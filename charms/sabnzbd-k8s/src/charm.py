#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd Charm."""

import logging
from typing import NamedTuple

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

from _sabnzbd import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    HEALTH_CHECK_URL,
    SERVICE_NAME,
    WEBUI_PORT,
    SABnzbdApi,
    reconcile_sabnzbd_config,
)
from charmarr_lib.core import (
    DownloadClient,
    DownloadClientType,
    K8sResourceManager,
    ensure_pebble_user,
    generate_api_key,
    get_secret_rotation_policy,
    observe_events,
    reconcilable_events_k8s,
    reconcile_storage_volume,
)
from charmarr_lib.core.constants import MEDIA_TYPE_DOWNLOAD_PATHS
from charmarr_lib.core.interfaces import (
    DownloadClientProvider,
    DownloadClientProviderData,
    MediaStorageRequirer,
)
from charmarr_lib.vpn import reconcile_gateway_client
from charmarr_lib.vpn.interfaces import VPNGatewayRequirer, VPNGatewayRequirerData

logger = logging.getLogger(__name__)


class ApiKey(NamedTuple):
    """API key credentials."""

    api_key: str
    secret_id: str


class SABnzbdCharm(ops.CharmBase):
    """SABnzbd download client charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._download_client = DownloadClientProvider(self, "download-client")
        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="download-client",
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
        framework.observe(self._media_storage.on.changed, self._reconcile)
        framework.observe(self._vpn_gateway.on.changed, self._reconcile)
        framework.observe(self.on["download-client"].relation_changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self._ingress.on.ready, self._configure_ingress)
        framework.observe(self.on.config_changed, self._configure_ingress)
        framework.observe(self.on.secret_rotate, self._on_secret_rotate)

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
        url_base = str(self.config.get("ingress-path", "/sabnzbd"))
        return url_base if url_base and url_base != "/" else None

    def _get_api_key(self) -> ApiKey | None:
        """Retrieve API key from Juju Secret, or None if not yet created."""
        try:
            secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
            content = secret.get_content(refresh=True)
            return ApiKey(
                api_key=content["api-key"],
                secret_id=self._get_secret_id(secret),
            )
        except ops.SecretNotFoundError:
            return None

    def _create_api_key(self) -> ApiKey:
        """Generate and store new API key in Juju Secret."""
        api_key = generate_api_key()
        secret = self.app.add_secret(
            {"api-key": api_key},
            label=API_KEY_SECRET_LABEL,
            description="SABnzbd API key",
            rotate=get_secret_rotation_policy(
                str(self.config.get("credential-rotation", "disabled"))
            ),
        )
        logger.info("Created API key secret")
        return ApiKey(
            api_key=api_key,
            secret_id=self._get_secret_id(secret),
        )

    def _reconcile_config(self, api_key: str) -> None:
        """Reconcile sabnzbd.ini with expected values, preserving user settings."""
        content = None
        if self._container.exists(CONFIG_FILE):
            content = self._container.pull(CONFIG_FILE).read()

        updated = reconcile_sabnzbd_config(
            content,
            api_key=api_key,
            app_name=self.app.name,
            url_base=self._get_url_base(),
        )

        if content != updated:
            self._container.push(CONFIG_FILE, updated, make_dirs=True)
            logger.info("Reconciled sabnzbd.ini")

    def _prepare_config_directory(self, puid: int, pgid: int) -> None:
        self._container.exec(["chown", "-R", f"{puid}:{pgid}", "/config"]).wait()

    def _is_service_running(self) -> bool:
        services = self._container.get_services(SERVICE_NAME)
        return bool(services) and services[SERVICE_NAME].is_running()

    def _build_readiness_check(self) -> dict:
        return {
            f"{CONTAINER_NAME}-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": HEALTH_CHECK_URL},
                "period": "10s",
                "timeout": "3s",
                "threshold": 3,
            }
        }

    def _build_pebble_layer(self, puid: int, pgid: int) -> ops.pebble.LayerDict:
        """Bypasses s6-overlay, runs SABnzbd directly.

        Port and host are read from sabnzbd.ini (set by build_sabnzbd_config).
        """
        return {
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    # LinuxServer installs deps in /lsiopy; /usr/bin/python3 won't find them
                    "command": "/lsiopy/bin/python3 /app/sabnzbd/SABnzbd.py -f /config/sabnzbd.ini",
                    "startup": "enabled",
                    "user-id": puid,
                    "group-id": pgid,
                    "environment": {
                        "HOME": "/config",
                        "TZ": str(self.config.get("timezone", "Etc/UTC")),
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
            killswitch=True,
        )

    def _get_api_client(self, api_key: ApiKey) -> SABnzbdApi:
        """Create authenticated API client for SABnzbd."""
        return SABnzbdApi(f"http://localhost:{WEBUI_PORT}", api_key.api_key)

    def _is_workload_ready(self, api_key: ApiKey) -> bool:
        """Check if SABnzbd workload is ready to accept API calls."""
        try:
            with self._get_api_client(api_key) as api:
                api.get_version()
                return True
        except Exception:
            return False

    def _configure_app(self, api_key: ApiKey) -> None:
        """Configure SABnzbd download paths via API."""
        with self._get_api_client(api_key) as api:
            api.set_config("misc", "complete_dir", "/data/usenet/complete")
            api.set_config("misc", "download_dir", "/data/usenet/incomplete")
            logger.info("Configured SABnzbd application settings")

    def _sync_categories(self, api_key: ApiKey) -> None:
        """Create SABnzbd categories for connected media managers.

        Each media manager (Radarr, Sonarr, etc.) gets a category named after its
        instance name, with the save path determined by its media type.
        SABnzbd uses relative paths from complete_dir.
        """
        requirers = self._download_client.get_requirers()
        if not requirers:
            return

        with self._get_api_client(api_key) as api:
            for requirer in requirers:
                folder = MEDIA_TYPE_DOWNLOAD_PATHS.get(requirer.manager, "other")
                api.set_config_category(requirer.instance_name, folder)
                logger.info(
                    "Created category %s with directory %s",
                    requirer.instance_name,
                    folder,
                )

    def _publish_download_client(self, api_key: ApiKey) -> None:
        """Publish download client data to all connected media managers.

        Grants the API key secret to each related app and publishes
        the DownloadClientProviderData with the secret ID.
        """
        secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
        for relation in self.model.relations.get("download-client", []):
            if relation.app:
                secret.grant(relation)

        data = DownloadClientProviderData(
            api_url=f"http://{self.app.name}:{WEBUI_PORT}",
            api_key_secret_id=api_key.secret_id,
            client=DownloadClient.SABNZBD,
            client_type=DownloadClientType.USENET,
            instance_name=self.app.name,
            base_path=self._get_url_base(),
        )
        self._download_client.publish_data(data)
        logger.info("Published download client provider data")

    def _configure_ingress(self, _: ops.EventBase) -> None:
        """Submit ingress route config to istio-ingress gateway."""
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        path = str(self.config.get("ingress-path", "/sabnzbd"))
        listener = Listener(port=443, protocol=ProtocolType.HTTP)

        config = IstioIngressRouteConfig(
            model=self.model.name,
            listeners=[listener],
            http_routes=[
                HTTPRoute(
                    name="sabnzbd",
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

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Non-leader: register readiness check (for K8s probe) and exit
        2. Wait for Pebble connection
        3. Wait for media-storage relation (provides PVC and PUID/PGID)
        4. Create API key if not exist
        5. Publish download client data to related media managers
        6. Write config file if not exist
        7. Mount shared storage PVC
        8. Reconcile VPN gateway client (if related)
        9. Configure Pebble layer and start service
        """
        # Non-leader: register readiness check so K8s removes from Service endpoints
        if not self.unit.is_leader():
            if self._container.can_connect():
                self._container.add_layer(
                    f"{CONTAINER_NAME}-check",
                    {"checks": self._build_readiness_check()},
                    combine=True,
                )
            return

        # Warn if scaled beyond 1 (leader still runs, non-leaders idle)
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

        if self._is_vpn_required():
            return

        # Ensure API key exists
        api_key = self._get_api_key() or self._create_api_key()

        # Publish download client data to related media managers
        self._publish_download_client(api_key)

        # Reconcile config - stops service if changes needed
        if self._is_service_running():
            self._container.stop(SERVICE_NAME)
        self._reconcile_config(api_key.api_key)

        # Fix config directory ownership for PUID/PGID
        self._prepare_config_directory(storage.puid, storage.pgid)

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
        ensure_pebble_user(self._container, storage.puid, storage.pgid, username="sab")

        # Configure Pebble layer and start service
        layer = self._build_pebble_layer(storage.puid, storage.pgid)
        self._container.add_layer(SERVICE_NAME, layer, combine=True)
        self._container.replan()

        # Expose WebUI port on the Kubernetes Service
        self.unit.set_ports(WEBUI_PORT)

        # Configure app via API once workload is ready
        if self._is_workload_ready(api_key):
            self._configure_app(api_key)
            self._sync_categories(api_key)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses. Framework picks the worst."""
        self._collect_scaling_status(event)
        self._collect_leader_status(event)
        self._collect_pebble_status(event)
        self._collect_storage_status(event)
        self._collect_vpn_requirement_status(event)
        self._collect_api_key_status(event)
        self._collect_vpn_status(event)
        self._collect_workload_status(event)

    def _collect_scaling_status(self, event: ops.CollectStatusEvent) -> None:
        """Block non-leader units when scaled beyond 1."""
        if self.app.planned_units() > 1 and not self.unit.is_leader():
            event.add_status(
                ops.BlockedStatus("Scaling not supported - only leader runs workload")
            )

    def _collect_leader_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for non-leader units."""
        if not self.unit.is_leader():
            event.add_status(ops.WaitingStatus("Standby (non-leader)"))

    def _collect_pebble_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for Pebble connectivity."""
        if not self._container.can_connect():
            event.add_status(ops.WaitingStatus("Waiting for Pebble"))

    def _collect_storage_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for storage relation."""
        if not self._media_storage.is_ready():
            event.add_status(ops.BlockedStatus("Waiting for media-storage relation"))

    def _is_vpn_required(self) -> bool:
        """Check if VPN is required based on unsafe-mode config."""
        unsafe_mode = bool(self.config.get("unsafe-mode", False))
        has_vpn_relation = self.model.get_relation("vpn-gateway") is not None
        return not unsafe_mode and not has_vpn_relation

    def _collect_vpn_requirement_status(self, event: ops.CollectStatusEvent) -> None:
        """Block when VPN is required but not configured."""
        if self._is_vpn_required():
            event.add_status(
                ops.BlockedStatus("Waiting for vpn-gateway relation (or set unsafe-mode=true)")
            )

    def _collect_vpn_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for VPN relation (optional)."""
        gateway = self._vpn_gateway.get_gateway()
        if gateway is not None and not gateway.vpn_connected:
            event.add_status(ops.WaitingStatus("Waiting for VPN connection"))

    def _collect_api_key_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for API key."""
        if not self.unit.is_leader():
            return
        if not self._get_api_key():
            event.add_status(ops.WaitingStatus("Waiting for API key"))

    def _collect_workload_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for workload health."""
        if not self.unit.is_leader():
            return
        if not self._container.can_connect():
            return
        if not self._media_storage.is_ready():
            return

        api_key = self._get_api_key()
        if not api_key:
            return

        if not self._is_workload_ready(api_key):
            event.add_status(ops.WaitingStatus("Waiting for workload"))
        else:
            event.add_status(ops.ActiveStatus())


if __name__ == "__main__":
    ops.main(SABnzbdCharm)
