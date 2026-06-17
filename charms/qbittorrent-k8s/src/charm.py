#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""qBittorrent Charm."""

import logging
from typing import NamedTuple

import ops
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.istio_beacon_k8s.v0.service_mesh import (
    AppPolicy,
    Endpoint,
    ServiceMeshConsumer,
    UnitPolicy,
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
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from charms.velero_libs.v0.velero_backup_config import VeleroBackupProvider, VeleroBackupSpec

from _qbittorrent import (
    CONFIG_FILE,
    CONTAINER_NAME,
    CREDENTIALS_SECRET_LABEL,
    DEFAULT_USERNAME,
    EXPORTER_COMMAND,
    EXPORTER_ENV_BASE_URL,
    EXPORTER_ENV_PASSWORD,
    EXPORTER_ENV_PORT,
    EXPORTER_ENV_USERNAME,
    HEALTH_CHECK_URL,
    METRICS_CONTAINER_NAME,
    METRICS_PATH,
    METRICS_PORT,
    METRICS_SERVICE_NAME,
    SERVICE_NAME,
    WEBUI_PORT,
    QBittorrentApi,
    compute_pbkdf2_hash,
    generate_password,
    reconcile_qbittorrent_config,
)
from charmarr_lib.core import (
    CharmarrChargedTopology,
    CharmarrTopologyRelation,
    DownloadClient,
    DownloadClientType,
    K8sResourceManager,
    MetricFamily,
    MetricSample,
    ensure_pebble_user,
    get_secret_rotation_policy,
    observe_events,
    reconcilable_events_k8s,
    reconcile_storage_volume,
    sync_secret_rotation_policy,
)
from charmarr_lib.core.constants import MEDIA_TYPE_DOWNLOAD_PATHS
from charmarr_lib.core.interfaces import (
    CrowsnestProvider,
    CrowsnestProviderData,
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
        self._exporter_container = self.unit.get_container(METRICS_CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._topology = CharmarrChargedTopology(
            self,
            relations=[
                CharmarrTopologyRelation("media-storage", role="requires", required=True),
                CharmarrTopologyRelation("vpn-gateway", role="requires", required=False),
                CharmarrTopologyRelation("download-client", role="provides", required=False),
            ],
            extra_exposition=self._build_charm_gauges,
        )
        self._metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[
                {"static_configs": [{"targets": [f"*:{METRICS_PORT}"]}]},
                self._topology.scrape_job,
            ],
            alert_rules_path=(
                "src/prometheus_alert_rules_extended"
                if bool(self.config.get("extended-alert-rules", False))
                else "src/prometheus_alert_rules"
            ),
            refresh_event=[self.on.qbittorrent_exporter_pebble_ready],
        )
        self._grafana_dashboards = GrafanaDashboardProvider(self)
        self._log_forwarder = LogForwarder(self, relation_name="logging")
        self._charm_tracing = ops.tracing.Tracing(self, tracing_relation_name="charm-tracing")

        self._download_client = DownloadClientProvider(self, "download-client")
        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")
        self._crowsnest = CrowsnestProvider(self, "crowsnest")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="download-client",
                    endpoints=[Endpoint(ports=[WEBUI_PORT])],
                ),
                AppPolicy(
                    relation="crowsnest",
                    endpoints=[Endpoint(ports=[self._topology.port])],
                ),
                UnitPolicy(
                    relation="metrics-endpoint",
                    ports=[METRICS_PORT, self._topology.port],
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
        self._ingress = IngressPerAppRequirer(self, port=WEBUI_PORT, strip_prefix=True)
        self._istio_ingress = IstioIngressRouteRequirer(self, relation_name="istio-ingress-route")

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self._media_storage.on.changed, self._reconcile)
        framework.observe(self._vpn_gateway.on.changed, self._reconcile)
        framework.observe(self.on["download-client"].relation_changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self.on.secret_rotate, self._on_secret_rotate)
        framework.observe(self._ingress.on.ready, self._reconcile)
        framework.observe(self._ingress.on.revoked, self._reconcile)

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

    def _configure_ingress(self) -> None:
        """Submit ingress route config to istio-ingress gateway."""
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        path = str(self.config["ingress-path"]) or f"/{self.app.name}"
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
        self._istio_ingress.submit_config(config)
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
        self._reconcile_exporter(new_credentials)

    def _build_exporter_layer(self, credentials: Credentials) -> ops.pebble.LayerDict:
        return {
            "summary": "qbittorrent-exporter Prometheus exporter",
            "services": {
                METRICS_SERVICE_NAME: {
                    "override": "replace",
                    "summary": "martabal/qbittorrent-exporter sidecar",
                    "command": EXPORTER_COMMAND,
                    "startup": "enabled",
                    "environment": {
                        EXPORTER_ENV_BASE_URL: f"http://localhost:{WEBUI_PORT}",
                        EXPORTER_ENV_USERNAME: credentials.username,
                        EXPORTER_ENV_PASSWORD: credentials.password,
                        EXPORTER_ENV_PORT: str(METRICS_PORT),
                    },
                },
            },
            "checks": {
                f"{METRICS_CONTAINER_NAME}-ready": {
                    "override": "replace",
                    "level": "ready",
                    "http": {"url": f"http://localhost:{METRICS_PORT}{METRICS_PATH}"},
                    "period": "10s",
                    "timeout": "3s",
                    "threshold": 3,
                }
            },
        }

    def _reconcile_exporter(self, credentials: Credentials) -> None:
        if not self._exporter_container.can_connect():
            return
        layer = self._build_exporter_layer(credentials)
        self._exporter_container.add_layer(METRICS_SERVICE_NAME, layer, combine=True)
        self._exporter_container.replan()

    def _build_charm_gauges(self) -> list[MetricFamily]:
        """Charm-state metrics published alongside topology.

        Currently: `charmarr_unsafe_mode_enabled` - whether the qbit charm
        is configured to allow torrent traffic without a VPN gateway
        relation. Crowsnest combines this with `charmarr_relation_bound{
        relation="vpn-gateway"}` to detect operators who turned the safety
        off without wiring gluetun (or whose gluetun went away).
        """
        unsafe = 1.0 if bool(self.config.get("unsafe-mode", False)) else 0.0
        return [
            MetricFamily(
                name="charmarr_unsafe_mode_enabled",
                help=(
                    "1 when the download client is configured to accept traffic "
                    "without a vpn-gateway relation (config: unsafe-mode=true), "
                    'else 0. Combine with charmarr_relation_bound{relation="vpn-gateway"} '
                    "to detect torrent traffic outside the tunnel."
                ),
                samples=[MetricSample(value=unsafe)],
            ),
        ]

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Refresh topology metrics + ensure topology daemon is running
        2. Non-leader: register readiness check (for K8s probe) and exit
        3. Submit ingress route config (if ingress relation exists)
        4. Wait for Pebble connection
        5. Wait for media-storage relation (provides PVC and PUID/PGID)
        6. Create credentials if not exist
        7. Publish download client data to related media managers
        8. Write config file if not exist
        9. Mount shared storage PVC
        10. Reconcile VPN gateway client (if related)
        11. Configure Pebble layer and start service
        """
        self._topology.reconcile()
        # The topology endpoint is a cluster-internal concern - crowsnest polls
        # it from inside the same K8s cluster. Hardcode the in-cluster Service
        # FQDN; never expose this URL externally.
        self._crowsnest.publish_data(
            CrowsnestProviderData(
                topology_url=(
                    f"http://{self.app.name}.{self.model.name}"
                    f".svc.cluster.local:{self._topology.port}/metrics"
                )
            )
        )

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

        self._configure_ingress()

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

        # Reconcile qbittorrent-exporter sidecar (Prometheus exporter)
        self._reconcile_exporter(credentials)

        # Expose WebUI port on the Kubernetes Service
        self.unit.set_ports(WEBUI_PORT, self._topology.port)

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
