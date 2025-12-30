#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Plex Media Server Charm."""

import logging

import ops
from charms.istio_beacon_k8s.v0.service_mesh import ServiceMeshConsumer
from charms.istio_ingress_k8s.v0.istio_ingress_route import (
    BackendRef,
    HTTPPathMatch,
    HTTPPathMatchType,
    HTTPRoute,
    HTTPRouteMatch,
    IstioIngressRouteConfig,
    IstioIngressRouteRequirer,
    Listener,
    ProtocolType,
)

from _plex import (
    CONTAINER_NAME,
    PLEX_BINARY,
    PLEX_DATA_DIR,
    PREFERENCES_FILE,
    SERVICE_NAME,
    WEBUI_PORT,
)
from charmarr_lib.core import (
    K8sResourceManager,
    ensure_pebble_user,
    observe_events,
    reconcilable_events_k8s,
    reconcile_hardware_transcoding,
    reconcile_storage_volume,
)
from charmarr_lib.core.interfaces import MediaStorageRequirer

logger = logging.getLogger(__name__)


class PlexCharm(ops.CharmBase):
    """Plex Media Server charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._service_mesh = ServiceMeshConsumer(self, policies=[])
        self._ingress = IstioIngressRouteRequirer(self, relation_name="istio-ingress-route")

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self._media_storage.on.changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self._ingress.on.ready, self._configure_ingress)

    @property
    def k8s(self) -> K8sResourceManager:
        """Lazily initialize K8s resource manager."""
        if self._k8s is None:
            self._k8s = K8sResourceManager()
        return self._k8s

    def _is_server_claimed(self) -> bool:
        """Check if Plex server is already claimed.

        A claimed server has a PlexOnlineToken in Preferences.xml.
        This token is written when the server is linked to a Plex account.
        """
        if not self._container.can_connect():
            return False

        try:
            content = self._container.pull(PREFERENCES_FILE).read()
            return "PlexOnlineToken" in content
        except (ops.pebble.PathError, FileNotFoundError):
            return False

    def _get_claim_token(self) -> str | None:
        """Get claim token from config if server is unclaimed.

        Returns None if:
        - Server is already claimed (token would be useless)
        - No claim token configured
        """
        if self._is_server_claimed():
            return None

        token = str(self.config.get("claim-token", "")).strip()
        return token if token else None

    def _is_service_running(self) -> bool:
        """Check if Plex service is running."""
        services = self._container.get_services(SERVICE_NAME)
        return bool(services) and services[SERVICE_NAME].is_running()

    def _build_readiness_check(self) -> dict:
        """Build Pebble readiness check using /identity endpoint."""
        health_url = f"http://localhost:{WEBUI_PORT}/identity"
        return {
            f"{CONTAINER_NAME}-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": health_url},
                "period": "10s",
                "timeout": "5s",
                "threshold": 3,
            }
        }

    def _build_pebble_layer(self, puid: int, pgid: int) -> ops.pebble.LayerDict:
        """Build Pebble layer - bypasses s6-overlay, runs Plex binary directly.

        Environment variables:
        - PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR: Config location
        - PLEX_CLAIM: Claim token for automated server setup (if unclaimed)
        - TZ: Timezone
        """
        env: dict[str, str] = {
            "HOME": "/config",
            "PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR": PLEX_DATA_DIR,
            "TZ": str(self.config.get("timezone", "Etc/UTC")),
        }

        claim_token = self._get_claim_token()
        if claim_token:
            env["PLEX_CLAIM"] = claim_token
            logger.info("Setting PLEX_CLAIM for automated server claiming")

        return {
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "command": PLEX_BINARY,
                    "startup": "enabled",
                    "user-id": puid,
                    "group-id": pgid,
                    "environment": env,
                }
            },
            "checks": self._build_readiness_check(),
        }

    def _reconcile_hardware_transcoding(self) -> None:
        """Reconcile hardware transcoding (/dev/dri mount) based on config."""
        enabled = bool(self.config.get("hardware-transcoding", False))
        reconcile_hardware_transcoding(
            manager=self.k8s,
            statefulset_name=self.app.name,
            namespace=self.model.name,
            container_name=CONTAINER_NAME,
            enabled=enabled,
        )

    def _configure_ingress(self, _: ops.EventBase) -> None:
        """Submit ingress route config to istio-ingress gateway.

        Note: Plex does not support URL path prefixes. Use a dedicated ingress.
        """
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        listener = Listener(port=443, protocol=ProtocolType.HTTP)

        config = IstioIngressRouteConfig(
            model=self.model.name,
            listeners=[listener],
            http_routes=[
                HTTPRoute(
                    name="plex",
                    listener=listener,
                    matches=[
                        HTTPRouteMatch(
                            path=HTTPPathMatch(
                                type=HTTPPathMatchType.PathPrefix,
                                value="/",
                            )
                        )
                    ],
                    backends=[BackendRef(service=self.app.name, port=WEBUI_PORT)],
                ),
            ],
        )
        self._ingress.submit_config(config)
        logger.info("Submitted ingress route config for Plex")

    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Non-leader: register readiness check and exit
        2. Wait for Pebble connection
        3. Wait for media-storage relation
        4. Mount shared storage PVC
        5. Reconcile hardware transcoding (if enabled)
        6. Configure Pebble layer with claim token (if unclaimed)
        7. Start workload
        """
        if not self.unit.is_leader():
            if self._container.can_connect():
                self._container.add_layer(
                    f"{CONTAINER_NAME}-check",
                    {"checks": self._build_readiness_check()},
                    combine=True,
                )
            return

        if self.app.planned_units() > 1:
            logger.warning(
                "Scaling > 1 not supported. Non-leader units are idle. "
                "Run: juju scale-application %s 1",
                self.app.name,
            )

        if not self._container.can_connect():
            return

        storage = self._media_storage.get_provider()
        if not storage:
            return

        # Mount shared storage PVC
        reconcile_storage_volume(
            manager=self.k8s,
            statefulset_name=self.app.name,
            namespace=self.model.name,
            container_name=CONTAINER_NAME,
            pvc_name=storage.pvc_name,
            mount_path=storage.mount_path,
            pgid=storage.pgid,
        )

        # Reconcile hardware transcoding
        self._reconcile_hardware_transcoding()

        # Fix /config ownership (Juju storage mounts as root)
        self._container.exec(["chown", "-R", f"{storage.puid}:{storage.pgid}", "/config"]).wait()

        # Ensure Plex data directory exists
        self._container.exec(
            ["mkdir", "-p", PLEX_DATA_DIR],
            user_id=storage.puid,
            group_id=storage.pgid,
        ).wait()

        # Plex codecs require /run/plex-temp (created by s6-overlay in LinuxServer image)
        self._container.exec(["mkdir", "-p", "/run/plex-temp"]).wait()
        self._container.exec(["chown", f"{storage.puid}:{storage.pgid}", "/run/plex-temp"]).wait()

        # Ensure user/group exist for Pebble's user-id/group-id
        ensure_pebble_user(self._container, storage.puid, storage.pgid, username="plex")

        # Configure Pebble layer and start service
        layer = self._build_pebble_layer(storage.puid, storage.pgid)
        self._container.add_layer(SERVICE_NAME, layer, combine=True)
        self._container.replan()

        self.unit.set_ports(WEBUI_PORT)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses. Framework picks the worst."""
        self._collect_scaling_status(event)
        self._collect_leader_status(event)
        self._collect_pebble_status(event)
        self._collect_storage_status(event)
        self._collect_workload_status(event)

    def _collect_scaling_status(self, event: ops.CollectStatusEvent) -> None:
        """Report blocked if scaling beyond 1 unit."""
        if self.app.planned_units() > 1 and not self.unit.is_leader():
            event.add_status(
                ops.BlockedStatus("Scaling not supported - only leader runs workload")
            )

    def _collect_leader_status(self, event: ops.CollectStatusEvent) -> None:
        """Report standby for non-leader units."""
        if not self.unit.is_leader():
            event.add_status(ops.WaitingStatus("Standby (non-leader)"))

    def _collect_pebble_status(self, event: ops.CollectStatusEvent) -> None:
        """Report waiting if Pebble not connected."""
        if not self._container.can_connect():
            event.add_status(ops.WaitingStatus("Waiting for Pebble"))

    def _collect_storage_status(self, event: ops.CollectStatusEvent) -> None:
        """Report blocked if media-storage relation missing."""
        if not self._media_storage.is_ready():
            event.add_status(ops.BlockedStatus("Waiting for media-storage relation"))

    def _collect_workload_status(self, event: ops.CollectStatusEvent) -> None:
        """Report workload status including claim state."""
        if not self.unit.is_leader():
            return
        if not self._container.can_connect():
            return
        if not self._media_storage.is_ready():
            return

        if not self._is_service_running():
            event.add_status(ops.WaitingStatus("Waiting for workload"))
            return

        if self._is_server_claimed():
            event.add_status(ops.ActiveStatus())
        else:
            event.add_status(ops.ActiveStatus("Running (unclaimed - sign in via web UI)"))


if __name__ == "__main__":
    ops.main(PlexCharm)
