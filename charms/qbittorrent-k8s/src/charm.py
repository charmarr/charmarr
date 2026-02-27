#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""qBittorrent Charm."""

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
    PathModifier,
    PathModifierType,
    ProtocolType,
    RequestRedirectFilter,
    RequestRedirectSpec,
    URLRewriteFilter,
    URLRewriteSpec,
)
from charms.velero_libs.v0.velero_backup_config import VeleroBackupProvider, VeleroBackupSpec

from _qbittorrent import (
    CONFIG_FILE,
    CONTAINER_NAME,
    CREDENTIALS_SECRET_LABEL,
    DEFAULT_USERNAME,
    HEALTH_CHECK_URL,
    SERVICE_NAME,
    WEBUI_PORT,
    QBittorrentApi,
    compute_pbkdf2_hash,
    generate_password,
    reconcile_qbittorrent_config,
)
from charmarr_lib.core import (
    DownloadClient,
    DownloadClientType,
    K8sResourceManager,
    ensure_pebble_user,
    get_secret_rotation_policy,
    observe_events,
    reconcilable_events_k8s,
    reconcile_storage_volume,
    sync_secret_rotation_policy,
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


class Credentials(NamedTuple):
    """WebUI credentials."""

    username: str
    password: str
    secret_id: str


class QBittorrentCharm(ops.CharmBase):
    """qBittorrent download client charm."""

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

    @property
    def _internal_url(self) -> str:
        """Internal K8s service URL for cross-namespace communication."""
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{WEBUI_PORT}"

    def _get_secret_id(self, secret: ops.Secret) -> str:
        """Get secret ID reliably (handles ops 2.x quirk with labeled secrets)."""
        if secret.id:
            return secret.id
        return secret.get_info().id

    def _get_credentials(self) -> Credentials | None:
        """Retrieve credentials from Juju Secret, or None if not yet created."""
        try:
            secret = self.model.get_secret(label=CREDENTIALS_SECRET_LABEL)
            content = secret.get_content(refresh=True)
            return Credentials(
                username=content["username"],
                password=content["password"],
                secret_id=self._get_secret_id(secret),
            )
        except ops.SecretNotFoundError:
            return None

    def _create_credentials(self) -> Credentials:
        """Generate and store new credentials in Juju Secret."""
        username = DEFAULT_USERNAME
        password = generate_password()
        secret = self.app.add_secret(
            {"username": username, "password": password},
            label=CREDENTIALS_SECRET_LABEL,
            description="qBittorrent WebUI credentials",
            rotate=get_secret_rotation_policy(
                str(self.config.get("credential-rotation", "disabled"))
            ),
        )
        logger.info("Created credentials secret")
        return Credentials(
            username=username,
            password=password,
            secret_id=self._get_secret_id(secret),
        )

    def _reconcile_config(self, credentials: Credentials) -> None:
        """Reconcile qBittorrent.conf with expected values, preserving user settings."""
        content = None
        if self._container.exists(CONFIG_FILE):
            content = self._container.pull(CONFIG_FILE).read()

        password_hash = compute_pbkdf2_hash(credentials.password)
        updated = reconcile_qbittorrent_config(
            content,
            username=credentials.username,
            password_hash=password_hash,
        )

        if content != updated:
            self._container.push(CONFIG_FILE, updated, make_dirs=True)
            logger.info("Reconciled qBittorrent config")

    def _prepare_config_directory(self, puid: int, pgid: int) -> None:
        self._container.exec(["chown", "-R", f"{puid}:{pgid}", "/config/qBittorrent"]).wait()

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
        """Bypasses s6-overlay, runs qbittorrent-nox directly."""
        return {
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "command": "/usr/bin/qbittorrent-nox --profile=/config",
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

    def _get_api_client(self, credentials: Credentials) -> QBittorrentApi:
        """Create authenticated API client for qBittorrent WebUI."""
        api = QBittorrentApi(f"http://localhost:{WEBUI_PORT}")
        api.authenticate(credentials.username, credentials.password)
        return api

    def _is_workload_ready(self, credentials: Credentials) -> bool:
        """Check if qBittorrent workload is ready to accept API calls."""
        try:
            with self._get_api_client(credentials) as api:
                api.get_version()
                return True
        except Exception:
            return False

    def _configure_app(self, credentials: Credentials) -> None:
        """Apply Trash Guides recommended settings via API."""
        with self._get_api_client(credentials) as api:
            prefs = {
                "save_path": "/data/torrents",
                "auto_tmm_enabled": True,
                "torrent_changed_tmm_enabled": True,
                "category_changed_tmm_enabled": True,
                "save_path_changed_tmm_enabled": True,
            }
            api.set_preferences(prefs)
            logger.info("Configured qBittorrent application settings")

    def _sync_categories(self, credentials: Credentials) -> None:
        """Create qBittorrent categories for connected media managers.

        Each media manager (Radarr, Sonarr, etc.) gets a category named after its
        instance name, with the save path determined by its media type.
        """
        requirers = self._download_client.get_requirers()
        if not requirers:
            return

        with self._get_api_client(credentials) as api:
            for requirer in requirers:
                folder = MEDIA_TYPE_DOWNLOAD_PATHS.get(requirer.manager, "other")
                save_path = f"/data/torrents/{folder}"
                api.create_category(requirer.instance_name, save_path)
                logger.info(
                    "Created category %s with save path %s",
                    requirer.instance_name,
                    save_path,
                )

    def _publish_download_client(self, credentials: Credentials) -> None:
        """Publish download client data to all connected media managers.

        Grants the credentials secret to each related app and publishes
        the DownloadClientProviderData with the secret ID.
        """
        secret = self.model.get_secret(label=CREDENTIALS_SECRET_LABEL)
        for relation in self.model.relations.get("download-client", []):
            if relation.app:
                secret.grant(relation)

        data = DownloadClientProviderData(
            api_url=self._internal_url,
            credentials_secret_id=credentials.secret_id,
            client=DownloadClient.QBITTORRENT,
            client_type=DownloadClientType.TORRENT,
            instance_name=self.app.name,
        )
        # NOTE: We intentionally don't publish the base path as qBittorrent serves endpoints at root.
        self._download_client.publish_data(data)
        logger.info("Published download client provider data")

    def _configure_ingress(self, _: ops.EventBase) -> None:
        """Submit ingress route config to istio-ingress gateway."""
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        path = str(self.config.get("ingress-path", "/qbt"))
        path_with_slash = path.rstrip("/") + "/"
        listener = Listener(port=int(self.config["ingress-port"]), protocol=ProtocolType.HTTP)

        config = IstioIngressRouteConfig(
            model=self.model.name,
            listeners=[listener],
            http_routes=[
                HTTPRoute(
                    name="qbittorrent-redirect",
                    listener=listener,
                    matches=[
                        HTTPRouteMatch(
                            path=HTTPPathMatch(
                                type=HTTPPathMatchType.Exact,
                                value=path.rstrip("/"),
                            )
                        )
                    ],
                    backends=[],
                    filters=[
                        RequestRedirectFilter(
                            requestRedirect=RequestRedirectSpec(
                                path=PathModifier(
                                    type=PathModifierType.ReplaceFullPath,
                                    value=path_with_slash,
                                ),
                                statusCode=301,
                            )
                        )
                    ],
                ),
                HTTPRoute(
                    name="qbittorrent",
                    listener=listener,
                    matches=[
                        HTTPRouteMatch(
                            path=HTTPPathMatch(
                                type=HTTPPathMatchType.PathPrefix,
                                value=path_with_slash,
                            )
                        )
                    ],
                    backends=[BackendRef(service=self.app.name, port=WEBUI_PORT)],
                    filters=[
                        URLRewriteFilter(
                            urlRewrite=URLRewriteSpec(
                                path=PathModifier(
                                    type=PathModifierType.ReplacePrefixMatch,
                                    value="/",
                                )
                            )
                        )
                    ],
                ),
            ],
        )
        self._ingress.submit_config(config)
        logger.info("Submitted ingress route config for path %s", path)

    def _on_secret_rotate(self, event: ops.SecretRotateEvent) -> None:
        """Handle secret rotation by generating new credentials."""
        if event.secret.label != CREDENTIALS_SECRET_LABEL:
            return
        if not self.unit.is_leader():
            return

        new_password = generate_password()
        event.secret.set_content({"username": DEFAULT_USERNAME, "password": new_password})
        logger.info("Rotated credentials secret")

        if not self._container.can_connect():
            return

        if self._is_service_running():
            self._container.stop(SERVICE_NAME)

        new_credentials = Credentials(
            username=DEFAULT_USERNAME,
            password=new_password,
            secret_id=self._get_secret_id(event.secret),
        )
        self._reconcile_config(new_credentials)
        self._container.replan()

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Non-leader: register readiness check (for K8s probe) and exit
        2. Wait for Pebble connection
        3. Wait for media-storage relation (provides PVC and PUID/PGID)
        4. Create credentials if not exist
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

        # Ensure credentials exist
        credentials = self._get_credentials()
        if credentials:
            secret = self.model.get_secret(label=CREDENTIALS_SECRET_LABEL)
            sync_secret_rotation_policy(
                secret, str(self.config.get("credential-rotation", "disabled"))
            )
        else:
            credentials = self._create_credentials()

        # Publish download client data to related media managers
        self._publish_download_client(credentials)

        # Reconcile config (preserves user settings like download paths)
        self._reconcile_config(credentials)

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
        ensure_pebble_user(self._container, storage.puid, storage.pgid, username="qbt")

        # Configure Pebble layer and start service
        layer = self._build_pebble_layer(storage.puid, storage.pgid)
        self._container.add_layer(SERVICE_NAME, layer, combine=True)
        self._container.replan()

        # Expose WebUI port on the Kubernetes Service
        self.unit.set_ports(WEBUI_PORT)

        # Configure app via API once workload is ready
        if self._is_workload_ready(credentials):
            self._configure_app(credentials)
            self._sync_categories(credentials)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses. Framework picks the worst."""
        self._collect_scaling_status(event)
        self._collect_leader_status(event)
        self._collect_pebble_status(event)
        self._collect_storage_status(event)
        self._collect_vpn_requirement_status(event)
        self._collect_credentials_status(event)
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

    def _collect_credentials_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for credentials."""
        if not self.unit.is_leader():
            return
        if not self._get_credentials():
            event.add_status(ops.WaitingStatus("Waiting for credentials"))

    def _collect_workload_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for workload health."""
        if not self.unit.is_leader():
            return
        if not self._container.can_connect():
            return
        if not self._media_storage.is_ready():
            return

        credentials = self._get_credentials()
        if not credentials:
            return

        if not self._is_workload_ready(credentials):
            event.add_status(ops.WaitingStatus("Waiting for workload"))
        else:
            event.add_status(ops.ActiveStatus())


if __name__ == "__main__":
    ops.main(QBittorrentCharm)
