#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Sonarr Charm."""

import logging

import ops
from charms.istio_beacon_k8s.v0.service_mesh import (
    AppPolicy,
    Endpoint,
    ServiceMeshConsumer,
)
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
from charms.velero_libs.v0.velero_backup_config import VeleroBackupProvider, VeleroBackupSpec

from _sonarr import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    SERVICE_NAME,
    WEBUI_PORT,
)
from charmarr_lib.core import (
    ArrApiClient,
    ArrApiError,
    K8sResourceManager,
    MediaManager,
    RecyclarrError,
    ensure_pebble_user,
    generate_api_key,
    get_secret_rotation_policy,
    observe_events,
    reconcilable_events_k8s,
    reconcile_config_xml,
    reconcile_download_clients,
    reconcile_root_folder,
    reconcile_storage_volume,
    sync_trash_profiles,
)
from charmarr_lib.core.interfaces import (
    DownloadClientRequirer,
    DownloadClientRequirerData,
    MediaIndexerRequirer,
    MediaIndexerRequirerData,
    MediaManagerProvider,
    MediaManagerProviderData,
    MediaStorageRequirer,
    QualityProfile,
)
from charmarr_lib.vpn import reconcile_gateway_client
from charmarr_lib.vpn.interfaces import VPNGatewayRequirer, VPNGatewayRequirerData

logger = logging.getLogger(__name__)


class SonarrCharm(ops.CharmBase):
    """Sonarr TV series collection manager charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._media_manager = MediaManagerProvider(self, "media-manager")
        self._media_indexer = MediaIndexerRequirer(self, "media-indexer")
        self._download_client = DownloadClientRequirer(self, "download-client")
        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="media-manager",
                    endpoints=[Endpoint(ports=[WEBUI_PORT])],
                ),
            ],
        )
        self._velero_backup = VeleroBackupProvider(
            self,
            relation_name="velero-backup-config",
            spec=VeleroBackupSpec(
                include_namespaces=[self.model.name],
                include_resources=["persistentvolumeclaims"],
                label_selector={"app.kubernetes.io/name": self.app.name},
                ttl="720h",
            ),
        )
        self._ingress = IstioIngressRouteRequirer(self, relation_name="istio-ingress-route")

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self._vpn_gateway.on.changed, self._reconcile)
        framework.observe(self._media_indexer.on.changed, self._reconcile)
        framework.observe(self._download_client.on.changed, self._reconcile)
        framework.observe(self._media_storage.on.changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self._ingress.on.ready, self._configure_ingress)
        framework.observe(self.on.config_changed, self._configure_ingress)
        framework.observe(self.on.secret_rotate, self._on_secret_rotate)
        framework.observe(self.on.rotate_api_key_action, self._on_rotate_api_key_action)
        framework.observe(self.on.sync_trash_profiles_action, self._on_sync_trash_profiles_action)

    @property
    def k8s(self) -> K8sResourceManager:
        """Lazily initialize K8s resource manager."""
        if self._k8s is None:
            self._k8s = K8sResourceManager()
        return self._k8s

    def _get_secret_id(self, secret: ops.Secret) -> str:
        """Get secret ID reliably (handles ops 2.x quirk with labeled secrets)."""
        if secret.id:
            return secret.id
        return secret.get_info().id

    def _get_url_base(self) -> str | None:
        """Get URL base path from config, or None if root/empty."""
        url_base = str(self.config.get("ingress-path", "/sonarr"))
        return url_base if url_base and url_base != "/" else None

    @property
    def _internal_url(self) -> str:
        """Internal K8s service URL for cross-namespace communication."""
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{WEBUI_PORT}"

    def _get_api_key_secret(self) -> tuple[str, str] | None:
        """Retrieve API key and secret ID from Juju Secret, or None if not yet created."""
        try:
            secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
            content = secret.get_content(refresh=True)
            return content["api-key"], self._get_secret_id(secret)
        except ops.SecretNotFoundError:
            return None

    def _create_api_key_secret(self, api_key: str) -> str:
        """Store API key in Juju Secret and return secret ID."""
        secret = self.app.add_secret(
            {"api-key": api_key},
            label=API_KEY_SECRET_LABEL,
            description="Sonarr API key",
            rotate=get_secret_rotation_policy(
                str(self.config.get("api-key-rotation", "disabled"))
            ),
        )
        logger.info("Created API key secret")
        return self._get_secret_id(secret)

    def _reconcile_config(self, api_key: str) -> None:
        """Reconcile config.xml with expected values, preserving user settings."""
        content = None
        if self._container.exists(CONFIG_FILE):
            content = self._container.pull(CONFIG_FILE).read()

        updated = reconcile_config_xml(
            content,
            api_key=api_key,
            url_base=self._get_url_base(),
            port=WEBUI_PORT,
            bind_address="*",
        )

        if content != updated:
            self._container.push(CONFIG_FILE, updated, make_dirs=True)
            logger.info("Reconciled config.xml")

    def _is_service_running(self) -> bool:
        services = self._container.get_services(SERVICE_NAME)
        return bool(services) and services[SERVICE_NAME].is_running()

    def _build_readiness_check(self) -> dict:
        url_base = self._get_url_base() or ""
        health_url = f"http://localhost:{WEBUI_PORT}{url_base}/ping"
        return {
            f"{CONTAINER_NAME}-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": health_url},
                "period": "10s",
                "timeout": "3s",
                "threshold": 3,
            }
        }

    def _build_pebble_layer(self, puid: int, pgid: int) -> ops.pebble.LayerDict:
        """Bypasses s6-overlay, runs Sonarr directly."""
        return {
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "command": "/app/sonarr/bin/Sonarr -nobrowser -data=/config",
                    "startup": "enabled",
                    "user-id": puid,
                    "group-id": pgid,
                    "environment": {
                        "HOME": "/config",
                        "TZ": str(self.config.get("timezone", "Etc/UTC")),
                        # Override TMPDIR - image sets it to /run/sonarr-temp which
                        # doesn't exist when bypassing s6-overlay; .NET needs it for
                        # atomic writes (e.g., ASP.NET Data Protection keys)
                        "TMPDIR": "/tmp",
                    },
                }
            },
            "checks": self._build_readiness_check(),
        }

    def _reconcile_vpn(self) -> None:
        """Reconcile VPN client-side patching based on gateway state."""
        if self.model.get_relation("vpn-gateway"):
            self._vpn_gateway.publish_data(VPNGatewayRequirerData(instance_name=self.app.name))

        gateway_data = self._vpn_gateway.get_gateway()
        reconcile_gateway_client(
            manager=self.k8s,
            statefulset_name=self.app.name,
            namespace=self.model.name,
            data=gateway_data,
            killswitch=False,
        )

    def _get_api_client(self, api_key: str) -> ArrApiClient:
        """Create authenticated API client for Sonarr."""
        url_base = self._get_url_base() or ""
        base_url = f"http://localhost:{WEBUI_PORT}{url_base}"
        return ArrApiClient(base_url, api_key)

    def _is_workload_ready(self, api_key: str) -> bool:
        """Check if Sonarr workload is ready to accept API calls."""
        try:
            with self._get_api_client(api_key) as api:
                api.get_host_config()
                return True
        except ArrApiError as e:
            logger.debug("Workload not ready: %s", e)
            return False

    def _get_secret_content(self, secret_id: str) -> dict[str, str]:
        """Retrieve secret content by ID for reconcilers."""
        secret = self.model.get_secret(id=secret_id)
        return secret.get_content(refresh=True)

    def _reconcile_download_clients(self, api_key: str) -> None:
        """Reconcile download clients in Sonarr."""
        providers = self._download_client.get_providers()
        if not providers:
            return

        with self._get_api_client(api_key) as api:
            reconcile_download_clients(
                api_client=api,
                desired_clients=providers,
                category=self.app.name,
                media_manager=MediaManager.SONARR,
                get_secret=self._get_secret_content,
            )

    def _get_root_folder_path(self) -> str:
        """Get root folder path based on is-4k config."""
        is_4k = bool(self.config.get("is-4k", False))
        return "/data/media/tv-uhd" if is_4k else "/data/media/tv"

    def _reconcile_root_folder(self, api_key: str, puid: int, pgid: int) -> None:
        """Ensure root folder exists in Sonarr based on is-4k config."""
        path = self._get_root_folder_path()
        self._container.exec(
            ["mkdir", "-p", path],
            user_id=puid,
            group_id=pgid,
        ).wait()
        with self._get_api_client(api_key) as api:
            reconcile_root_folder(api, path)

    def _sync_trash_profiles(self, api_key: str) -> None:
        """Sync Trash Guides quality profiles via Recyclarr."""
        profiles_config = str(self.config.get("trash-profiles", ""))
        if not profiles_config.strip():
            return

        container = self.unit.get_container("recyclarr")
        if not container.can_connect():
            logger.warning("Recyclarr container not ready, skipping profile sync")
            return

        sync_trash_profiles(
            container=container,
            manager=MediaManager.SONARR,
            api_key=api_key,
            profiles_config=profiles_config,
            port=WEBUI_PORT,
            base_url=self._get_url_base(),
        )

    def _get_quality_profiles(self, api_key: str) -> list[QualityProfile]:
        """Fetch quality profiles from Sonarr API."""
        try:
            with self._get_api_client(api_key) as api:
                profiles = api.get_quality_profiles()
                return [QualityProfile(id=p.id, name=p.name) for p in profiles]
        except ArrApiError as e:
            logger.debug("Failed to fetch quality profiles: %s", e)
            return []

    def _get_root_folders(self, api_key: str) -> list[str]:
        """Fetch root folders from Sonarr API."""
        try:
            with self._get_api_client(api_key) as api:
                folders = api.get_root_folders()
                return [f.path for f in folders]
        except ArrApiError as e:
            logger.debug("Failed to fetch root folders: %s", e)
            return []

    def _publish_media_manager(self, api_key: str, secret_id: str) -> None:
        """Publish media manager data to all connected applications."""
        secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
        for relation in self.model.relations.get("media-manager", []):
            if relation.app:
                secret.grant(relation)

        quality_profiles = self._get_quality_profiles(api_key)
        root_folders = self._get_root_folders(api_key)
        is_4k = bool(self.config.get("is-4k", False))

        data = MediaManagerProviderData(
            api_url=self._internal_url,
            api_key_secret_id=secret_id,
            manager=MediaManager.SONARR,
            instance_name=self.app.name,
            base_path=self._get_url_base(),
            quality_profiles=quality_profiles,
            root_folders=root_folders,
            is_4k=is_4k,
        )
        self._media_manager.publish_data(data)
        logger.info("Published media manager provider data")

    def _publish_media_indexer_requirer(self, secret_id: str) -> None:
        """Publish requirer data to media-indexer (Prowlarr) relation."""
        relation = self.model.get_relation("media-indexer")
        if not relation:
            return

        secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
        if relation.app:
            secret.grant(relation)

        data = MediaIndexerRequirerData(
            api_url=self._internal_url,
            api_key_secret_id=secret_id,
            manager=MediaManager.SONARR,
            instance_name=self.app.name,
            base_path=self._get_url_base(),
        )
        self._media_indexer.publish_data(data)
        logger.info("Published media indexer requirer data")

    def _publish_download_client_requirer(self) -> None:
        """Publish requirer data to download-client relations."""
        if not self.model.relations.get("download-client"):
            return
        data = DownloadClientRequirerData(
            manager=MediaManager.SONARR,
            instance_name=self.app.name,
        )
        self._download_client.publish_data(data)
        logger.info("Published download client requirer data")

    def _configure_ingress(self, _: ops.EventBase) -> None:
        """Submit ingress route config to istio-ingress gateway."""
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        path = str(self.config.get("ingress-path", "/sonarr"))
        listener = Listener(port=443, protocol=ProtocolType.HTTP)

        config = IstioIngressRouteConfig(
            model=self.model.name,
            listeners=[listener],
            http_routes=[
                HTTPRoute(
                    name="sonarr",
                    listener=listener,
                    matches=[
                        HTTPRouteMatch(
                            path=HTTPPathMatch(
                                type=HTTPPathMatchType.PathPrefix,
                                value=path,
                            )
                        )
                    ],
                    backends=[BackendRef(service=self.app.name, port=WEBUI_PORT)],
                ),
            ],
        )
        self._ingress.submit_config(config)
        logger.info("Submitted ingress route config for path %s", path)

    def _on_secret_rotate(self, event: ops.SecretRotateEvent) -> None:
        """Handle secret rotation by generating new API key."""
        if event.secret.label != API_KEY_SECRET_LABEL:
            return
        if not self.unit.is_leader():
            return

        new_api_key = generate_api_key()
        event.secret.set_content({"api-key": new_api_key})
        logger.info("Rotated API key secret")

        if not self._container.can_connect():
            return

        if self._is_service_running():
            self._container.stop(SERVICE_NAME)

        self._reconcile_config(new_api_key)
        self._container.replan()

    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Non-leader: register readiness check (for K8s probe) and exit
        2. Wait for Pebble connection
        3. Ensure API key exists in Juju secret
        4. Write config file if missing or API key mismatch
        5. Reconcile VPN gateway client (if related)
        6. Configure Pebble layer and start service
        7. Once workload ready:
           - Sync Trash Guides profiles via Recyclarr (if configured)
           - Reconcile download clients from relations
           - Reconcile root folder from config
           - Publish media-manager data to related apps
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

        # Ensure API key exists (charm creates it, not the app)
        secret_data = self._get_api_key_secret()
        if secret_data:
            api_key, secret_id = secret_data
        else:
            api_key = generate_api_key()
            secret_id = self._create_api_key_secret(api_key)

        # Publish requirer data to media-indexer (Prowlarr) relation
        self._publish_media_indexer_requirer(secret_id)

        # Publish requirer data to download-client relations
        self._publish_download_client_requirer()

        # Reconcile config.xml (preserves user settings like authentication)
        self._reconcile_config(api_key)

        # Fix /config ownership (Juju storage mounts as root)
        self._container.exec(["chown", "-R", f"{storage.puid}:{storage.pgid}", "/config"]).wait()

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

        # Reconcile VPN gateway client
        self._reconcile_vpn()

        # Ensure user/group exist for Pebble's user-id/group-id
        ensure_pebble_user(self._container, storage.puid, storage.pgid, username="sonarr")

        # Configure Pebble layer and start service
        layer = self._build_pebble_layer(storage.puid, storage.pgid)
        self._container.add_layer(SERVICE_NAME, layer, combine=True)
        self._container.replan()

        self.unit.set_ports(WEBUI_PORT)

        if self._is_workload_ready(api_key):
            # Sync Trash Guides profiles (runs recyclarr if trash-profiles configured)
            try:
                self._sync_trash_profiles(api_key)
            except RecyclarrError as e:
                logger.error("Failed to sync Trash Guides profiles: %s", e)

            # Reconcile download clients from relations
            self._reconcile_download_clients(api_key)

            # Reconcile root folder from config
            self._reconcile_root_folder(api_key, storage.puid, storage.pgid)

            # Publish media manager data to related apps
            self._publish_media_manager(api_key, secret_id)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses. Framework picks the worst."""
        self._collect_scaling_status(event)
        self._collect_leader_status(event)
        self._collect_pebble_status(event)
        self._collect_storage_status(event)
        self._collect_api_key_status(event)
        self._collect_vpn_status(event)
        self._collect_workload_status(event)

    def _collect_scaling_status(self, event: ops.CollectStatusEvent) -> None:
        if self.app.planned_units() > 1 and not self.unit.is_leader():
            event.add_status(
                ops.BlockedStatus("Scaling not supported - only leader runs workload")
            )

    def _collect_leader_status(self, event: ops.CollectStatusEvent) -> None:
        if not self.unit.is_leader():
            event.add_status(ops.WaitingStatus("Standby (non-leader)"))

    def _collect_pebble_status(self, event: ops.CollectStatusEvent) -> None:
        if not self._container.can_connect():
            event.add_status(ops.WaitingStatus("Waiting for Pebble"))

    def _collect_storage_status(self, event: ops.CollectStatusEvent) -> None:
        if not self._media_storage.is_ready():
            event.add_status(ops.BlockedStatus("Waiting for media-storage relation"))

    def _collect_vpn_status(self, event: ops.CollectStatusEvent) -> None:
        gateway = self._vpn_gateway.get_gateway()
        if gateway is not None and not gateway.vpn_connected:
            event.add_status(ops.WaitingStatus("Waiting for VPN connection"))

    def _collect_api_key_status(self, event: ops.CollectStatusEvent) -> None:
        # Leader-only: non-leaders report standby via _collect_leader_status
        if not self.unit.is_leader():
            return
        if not self._get_api_key_secret():
            event.add_status(ops.WaitingStatus("Waiting for API key"))

    def _collect_workload_status(self, event: ops.CollectStatusEvent) -> None:
        # Leader-only: non-leaders report standby via _collect_leader_status
        if not self.unit.is_leader():
            return
        if not self._container.can_connect():
            return

        secret_data = self._get_api_key_secret()
        if not secret_data:
            return

        api_key, _ = secret_data
        if not self._is_workload_ready(api_key):
            event.add_status(ops.WaitingStatus("Waiting for workload"))
        else:
            event.add_status(ops.ActiveStatus())

    def _on_rotate_api_key_action(self, event: ops.ActionEvent) -> None:
        """Handle rotate-api-key action."""
        if not self.unit.is_leader():
            event.fail("This action can only run on the leader unit")
            return

        if not self._container.can_connect():
            event.fail("Cannot connect to Pebble")
            return

        new_api_key = generate_api_key()
        self._reconcile_config(new_api_key)

        try:
            secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
            secret.set_content({"api-key": new_api_key})
            logger.info("Rotated API key via action")
        except ops.SecretNotFoundError:
            self._create_api_key_secret(new_api_key)

        if self._is_service_running():
            self._container.stop(SERVICE_NAME)
            self._container.start(SERVICE_NAME)
            logger.info("Restarted Sonarr after API key rotation")

        event.set_results({"result": "API key rotated successfully"})

    def _on_sync_trash_profiles_action(self, event: ops.ActionEvent) -> None:
        """Handle sync-trash-profiles action."""
        if not self.unit.is_leader():
            event.fail("This action can only run on the leader unit")
            return

        secret_data = self._get_api_key_secret()
        if not secret_data:
            event.fail("No API key found")
            return

        api_key, _ = secret_data
        profiles_config = str(self.config.get("trash-profiles", ""))
        if not profiles_config.strip():
            event.fail("No trash-profiles configured")
            return

        try:
            self._sync_trash_profiles(api_key)
            event.set_results({"result": "Trash profiles synced successfully"})
        except RecyclarrError as e:
            event.fail(f"Recyclarr sync failed: {e}")


if __name__ == "__main__":
    ops.main(SonarrCharm)
