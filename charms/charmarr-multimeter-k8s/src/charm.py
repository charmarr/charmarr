#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr Multimeter - test utility charm for validating interface providers."""

import logging

import ops
from charms.istio_beacon_k8s.v0.service_mesh import ServiceMeshConsumer

from _http_actions import handle_http_request
from _mock_nfs import cleanup_nfs_server, deploy_nfs_server
from _storage_actions import (
    handle_get_mounts,
    handle_get_pv,
    handle_get_pvc,
    handle_get_security_context,
)
from _vpn_test_actions import (
    handle_check_configmap,
    handle_check_connectivity,
    handle_check_network_policy,
    handle_check_vxlan_interface,
    handle_get_container_env,
    handle_get_external_ip,
    handle_get_gateway_client_config,
    handle_get_statefulset_containers,
)
from charmarr_lib.core import (
    K8sResourceManager,
    MediaManager,
    RequestManager,
    observe_events,
    reconcilable_events_k8s,
    reconcile_storage_volume,
)
from charmarr_lib.core.interfaces import (
    DownloadClientRequirer,
    DownloadClientRequirerData,
    MediaIndexerRequirer,
    MediaIndexerRequirerData,
    MediaManagerRequirer,
    MediaManagerRequirerData,
    MediaStorageRequirer,
    MediaStorageRequirerData,
)
from charmarr_lib.vpn import reconcile_gateway_client
from charmarr_lib.vpn.interfaces import VPNGatewayRequirer, VPNGatewayRequirerData

logger = logging.getLogger(__name__)

CONTAINER_NAME = "multimeter"


class CharmarrMultimeterCharm(ops.CharmBase):
    """Test utility charm implementing requirer side of all Charmarr interfaces."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._media_indexer = MediaIndexerRequirer(self, "media-indexer")
        self._download_client = DownloadClientRequirer(self, "download-client")
        self._media_manager = MediaManagerRequirer(self, "media-manager")
        self._vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")
        self._service_mesh = ServiceMeshConsumer(self)
        self._k8s: K8sResourceManager | None = None

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self.on.get_pvc_action, self._on_get_pvc_action)
        framework.observe(self.on.get_pv_action, self._on_get_pv_action)
        framework.observe(self.on.deploy_nfs_server_action, self._on_deploy_nfs_server_action)
        framework.observe(self.on.cleanup_nfs_server_action, self._on_cleanup_nfs_server_action)
        framework.observe(self.on.get_mounts_action, self._on_get_mounts_action)
        framework.observe(
            self.on.get_security_context_action, self._on_get_security_context_action
        )
        # VPN testing actions
        framework.observe(self.on.get_external_ip_action, self._on_get_external_ip_action)
        framework.observe(
            self.on.check_vxlan_interface_action, self._on_check_vxlan_interface_action
        )
        framework.observe(self.on.check_connectivity_action, self._on_check_connectivity_action)
        framework.observe(
            self.on.get_statefulset_containers_action, self._on_get_statefulset_containers_action
        )
        framework.observe(self.on.get_container_env_action, self._on_get_container_env_action)
        framework.observe(
            self.on.check_network_policy_action, self._on_check_network_policy_action
        )
        framework.observe(self.on.check_configmap_action, self._on_check_configmap_action)
        framework.observe(
            self.on.get_gateway_client_config_action, self._on_get_gateway_client_config_action
        )
        framework.observe(self.on.http_request_action, self._on_http_request_action)

    @property
    def k8s(self) -> K8sResourceManager:
        if self._k8s is None:
            self._k8s = K8sResourceManager()
        return self._k8s

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile workload and publish requirer data."""
        if not self.unit.is_leader():
            return

        self._reconcile_storage()
        self._reconcile_pebble()

        instance_name = self.app.name

        if self.model.get_relation("media-storage"):
            self._media_storage.publish_data(MediaStorageRequirerData(instance_name=instance_name))

        if self.model.get_relation("media-indexer"):
            self._media_indexer.publish_data(
                MediaIndexerRequirerData(
                    api_url=f"http://{instance_name}:8080",
                    api_key_secret_id="placeholder",
                    manager=MediaManager.RADARR,
                    instance_name=instance_name,
                )
            )

        if self.model.get_relation("download-client"):
            self._download_client.publish_data(
                DownloadClientRequirerData(
                    manager=MediaManager.RADARR,
                    instance_name=instance_name,
                )
            )

        if self.model.get_relation("media-manager"):
            self._media_manager.publish_data(
                MediaManagerRequirerData(
                    requester=RequestManager.OVERSEERR,
                    instance_name=instance_name,
                )
            )

        if self.model.get_relation("vpn-gateway"):
            self._vpn_gateway.publish_data(VPNGatewayRequirerData(instance_name=instance_name))

        self._reconcile_vpn()

    def _reconcile_storage(self) -> None:
        """Mount or unmount shared storage based on relation state."""
        storage_data = self._media_storage.get_provider()
        reconcile_storage_volume(
            self.k8s,
            statefulset_name=self.app.name,
            namespace=self.model.name,
            container_name=CONTAINER_NAME,
            pvc_name=storage_data.pvc_name if storage_data else None,
            mount_path=storage_data.mount_path if storage_data else "/data",
            pgid=storage_data.pgid if storage_data else None,
        )

    def _reconcile_pebble(self) -> None:
        """Configure Pebble layer with user-id/group-id from storage relation."""
        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            return

        storage_data = self._media_storage.get_provider()

        service: dict = {
            "override": "replace",
            "command": "sleep infinity",
            "startup": "enabled",
        }

        if storage_data:
            service["user-id"] = storage_data.puid
            service["group-id"] = storage_data.pgid

        layer: ops.pebble.LayerDict = {"services": {"workload": service}}  # type: ignore[typeddict-item]
        container.add_layer("workload", layer, combine=True)
        container.replan()

    def _reconcile_vpn(self) -> None:
        """Reconcile VPN client-side patching based on gateway state."""
        gateway_data = self._vpn_gateway.get_gateway()

        reconcile_gateway_client(
            manager=self.k8s,
            statefulset_name=self.app.name,
            namespace=self.model.name,
            data=gateway_data,
            killswitch=True,
        )

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect unit status based on connected relations."""
        if not self.unit.is_leader():
            event.add_status(ops.ActiveStatus("Standby (leader manages relations)"))
            return

        connected = self._count_connected_relations()
        if connected == 0:
            event.add_status(ops.ActiveStatus("Ready (no relations)"))
        else:
            event.add_status(ops.ActiveStatus(f"Connected to {connected} provider(s)"))

    def _count_connected_relations(self) -> int:
        """Count number of relations with provider data available."""
        count = 0
        if self._media_storage.is_ready():
            count += 1
        if self._media_indexer.get_provider_data() is not None:
            count += 1
        if self._download_client.get_providers():
            count += 1
        if self._media_manager.get_providers():
            count += 1
        if self._vpn_gateway.get_gateway() is not None:
            count += 1
        if self._service_mesh.mesh_type() is not None:
            count += 1
        return count

    def _on_get_pvc_action(self, event: ops.ActionEvent) -> None:
        handle_get_pvc(event, self.k8s)

    def _on_get_pv_action(self, event: ops.ActionEvent) -> None:
        handle_get_pv(event, self.k8s)

    def _on_deploy_nfs_server_action(self, event: ops.ActionEvent) -> None:
        """Deploy a mock NFS server for testing."""
        timeout = event.params.get("timeout", 120)
        try:
            ip = deploy_nfs_server(self.k8s, self.model.name, timeout)
            event.set_results({"nfs-server-ip": ip, "nfs-path": "/"})
        except TimeoutError as e:
            event.fail(str(e))
        except Exception as e:
            event.fail(f"Failed to deploy NFS server: {e}")

    def _on_cleanup_nfs_server_action(self, event: ops.ActionEvent) -> None:
        """Remove the mock NFS server."""
        try:
            cleanup_nfs_server(self.k8s, self.model.name)
            event.set_results({"status": "removed"})
        except Exception as e:
            event.fail(f"Failed to cleanup NFS server: {e}")

    def _on_get_mounts_action(self, event: ops.ActionEvent) -> None:
        handle_get_mounts(event, self.unit.get_container(CONTAINER_NAME))

    def _on_get_security_context_action(self, event: ops.ActionEvent) -> None:
        handle_get_security_context(event, self.k8s, self.app.name, self.model.name)

    # VPN testing actions

    def _on_get_external_ip_action(self, event: ops.ActionEvent) -> None:
        handle_get_external_ip(event, self.unit.get_container(CONTAINER_NAME))

    def _on_check_vxlan_interface_action(self, event: ops.ActionEvent) -> None:
        handle_check_vxlan_interface(event, self.unit.get_container(CONTAINER_NAME))

    def _on_check_connectivity_action(self, event: ops.ActionEvent) -> None:
        handle_check_connectivity(event, self.unit.get_container(CONTAINER_NAME))

    def _on_get_statefulset_containers_action(self, event: ops.ActionEvent) -> None:
        handle_get_statefulset_containers(event, self.k8s)

    def _on_get_container_env_action(self, event: ops.ActionEvent) -> None:
        handle_get_container_env(event, self.k8s)

    def _on_check_network_policy_action(self, event: ops.ActionEvent) -> None:
        handle_check_network_policy(event, self.k8s)

    def _on_check_configmap_action(self, event: ops.ActionEvent) -> None:
        handle_check_configmap(event, self.k8s)

    def _on_get_gateway_client_config_action(self, event: ops.ActionEvent) -> None:
        handle_get_gateway_client_config(event, self.k8s, self.app.name, self.model.name)

    def _on_http_request_action(self, event: ops.ActionEvent) -> None:
        handle_http_request(event)


if __name__ == "__main__":
    ops.main(CharmarrMultimeterCharm)
