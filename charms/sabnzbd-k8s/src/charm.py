#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd Charm."""

import logging
from typing import NamedTuple

import httpx
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
    ProtocolType,
)
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.velero_libs.v0.velero_backup_config import VeleroBackupProvider, VeleroBackupSpec

from _sabnzbd import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    EXPORTER_COMMAND,
    EXPORTER_ENV_APIKEYS,
    EXPORTER_ENV_BASEURLS,
    EXPORTER_ENV_PORT,
    HEALTH_CHECK_URL,
    METRICS_CONTAINER_NAME,
    METRICS_PATH,
    METRICS_PORT,
    METRICS_SERVICE_NAME,
    SERVICE_NAME,
    WEBUI_PORT,
    SABnzbdApi,
    reconcile_sabnzbd_config,
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
    generate_api_key,
    get_config_hash,
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


class ApiKey(NamedTuple):
    """API key credentials."""

    api_key: str
    secret_id: str


class SABnzbdCharm(ops.CharmBase):
    """SABnzbd download client charm."""

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
            refresh_event=[self.on.sabnzbd_exporter_pebble_ready],
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
        self._ingress = IstioIngressRouteRequirer(self, relation_name="istio-ingress-route")

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self._media_storage.on.changed, self._reconcile)
        framework.observe(self._vpn_gateway.on.changed, self._reconcile)
        framework.observe(self.on["download-client"].relation_changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
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
        url_base = str(self.config["ingress-path"]) or f"/{self.app.name}"
        return url_base if url_base and url_base != "/" else None

    @property
    def _internal_url(self) -> str:
        """Internal K8s service URL for cross-namespace communication."""
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{WEBUI_PORT}"

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

        extra_allowed_hosts = str(self.config.get("host-whitelist", "")) or None

        updated, changed = reconcile_sabnzbd_config(
            content,
            api_key=api_key,
            app_name=self.app.name,
            url_base=self._get_url_base(),
            extra_allowed_hosts=extra_allowed_hosts,
        )

        if changed:
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
                        # SABnzbd reads url_base from sabnzbd.ini, not env, but including
                        # it here ensures Pebble restarts service when ingress-path changes
                        "__CHARM_URL_BASE": self._get_url_base() or "",
                        # Config hash triggers Pebble restart when sabnzbd.ini changes
                        "__CONFIG_HASH": get_config_hash(self._container, CONFIG_FILE),
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
            api_url=self._internal_url,
            api_key_secret_id=api_key.secret_id,
            client=DownloadClient.SABNZBD,
            client_type=DownloadClientType.USENET,
            instance_name=self.app.name,
            base_path=self._get_url_base(),
        )
        self._download_client.publish_data(data)
        logger.info("Published download client provider data")

    def _configure_ingress(self) -> None:
        """Submit ingress route config to istio-ingress gateway."""
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        path = str(self.config["ingress-path"]) or f"/{self.app.name}"
        listener = Listener(port=int(self.config["ingress-port"]), protocol=ProtocolType.HTTP)

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
        self._reconcile_exporter(new_api_key)

    def _build_exporter_layer(self, api_key: str) -> ops.pebble.LayerDict:
        return {
            "summary": "sabnzbd-exporter Prometheus exporter",
            "services": {
                METRICS_SERVICE_NAME: {
                    "override": "replace",
                    "summary": "msroest/sabnzbd_exporter sidecar",
                    "command": EXPORTER_COMMAND,
                    "startup": "enabled",
                    "environment": {
                        EXPORTER_ENV_BASEURLS: f"http://localhost:{WEBUI_PORT}/sabnzbd",
                        EXPORTER_ENV_APIKEYS: api_key,
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

    def _reconcile_exporter(self, api_key: str) -> None:
        if not self._exporter_container.can_connect():
            return
        layer = self._build_exporter_layer(api_key)
        self._exporter_container.add_layer(METRICS_SERVICE_NAME, layer, combine=True)
        self._exporter_container.replan()

    def _build_charm_gauges(self) -> list[MetricFamily]:
        """Charm-state metrics published alongside topology.

        - `charmarr_unsafe_mode_enabled` - whether sab is configured to allow
          downloads without a VPN gateway relation.
        - `charmarr_queue_item_size_bytes` / `_remaining_bytes` - one series per
          currently queued NZB, powering the fleet "active downloads" tables.
        """
        unsafe = 1.0 if bool(self.config.get("unsafe-mode", False)) else 0.0
        return [
            MetricFamily(
                name="charmarr_unsafe_mode_enabled",
                help=(
                    "1 when the download client is configured to accept traffic "
                    "without a vpn-gateway relation (config: unsafe-mode=true), "
                    'else 0. Combine with charmarr_relation_bound{relation="vpn-gateway"} '
                    "to detect usenet traffic outside the tunnel."
                ),
                samples=[MetricSample(value=unsafe)],
            ),
            *self._build_queue_gauges(),
        ]

    def _build_queue_gauges(self) -> list[MetricFamily]:
        """Poll SABnzbd's queue endpoint and emit one series per active slot.

        SABnzbd returns sizes as MB strings (e.g. `"1.2"`); converted to
        bytes here. Silent on workload-not-ready or empty queue - topology
        metrics still ship.
        """
        api_key = self._get_api_key()
        if not api_key:
            return []
        try:
            with self._get_api_client(api_key) as api:
                slots = api.get_queue()
        except (httpx.HTTPError, ValueError) as e:
            logger.debug("Queue poll failed: %s", e)
            return []

        if not slots:
            return []

        def mb_str_to_bytes(value: object) -> float:
            try:
                return float(str(value)) * 1024 * 1024
            except (TypeError, ValueError):
                return 0.0

        size_samples: list[MetricSample] = []
        remaining_samples: list[MetricSample] = []
        for slot in slots:
            labels = {
                "title": str(slot.get("filename", "")),
                "status": str(slot.get("status", "")),
                "category": str(slot.get("cat", "")),
            }
            size_samples.append(MetricSample(labels=labels, value=mb_str_to_bytes(slot.get("mb"))))
            remaining_samples.append(
                MetricSample(labels=labels, value=mb_str_to_bytes(slot.get("mbleft")))
            )

        return [
            MetricFamily(
                name="charmarr_queue_item_size_bytes",
                help="Total size in bytes of a currently queued NZB.",
                samples=size_samples,
            ),
            MetricFamily(
                name="charmarr_queue_item_remaining_bytes",
                help="Bytes remaining to download for a currently queued NZB.",
                samples=remaining_samples,
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
        6. Create API key if not exist
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

        # Ensure API key exists
        api_key = self._get_api_key()
        if api_key:
            secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
            sync_secret_rotation_policy(
                secret, str(self.config.get("credential-rotation", "disabled"))
            )
        else:
            api_key = self._create_api_key()

        # Publish download client data to related media managers
        self._publish_download_client(api_key)

        # Reconcile config - Pebble auto-restarts via __CONFIG_HASH env var
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

        # Reconcile sabnzbd-exporter sidecar (Prometheus exporter)
        self._reconcile_exporter(api_key.api_key)

        # Expose WebUI port on the Kubernetes Service
        self.unit.set_ports(WEBUI_PORT, self._topology.port)

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
