#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Sonarr Charm."""

import logging

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

from _sonarr import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    METRICS_CONTAINER_NAME,
    METRICS_PATH,
    METRICS_PORT,
    METRICS_SERVICE_NAME,
    SCRAPARR_COMMAND,
    SCRAPARR_ENV_API_KEY,
    SCRAPARR_ENV_DETAILED,
    SCRAPARR_ENV_URL,
    SERVICE_NAME,
    WEBUI_PORT,
)
from charmarr_lib.core import (
    ArrApiClient,
    ArrApiError,
    CharmarrChargedTopology,
    CharmarrTopologyRelation,
    ContentVariant,
    K8sResourceManager,
    MediaManager,
    MetricFamily,
    MetricSample,
    RecyclarrError,
    ensure_pebble_user,
    generate_api_key,
    get_default_trash_profiles,
    get_root_folder,
    get_secret_rotation_policy,
    observe_events,
    reconcilable_events_k8s,
    reconcile_config_xml,
    reconcile_download_clients,
    reconcile_root_folder,
    reconcile_storage_volume,
    sync_secret_rotation_policy,
    sync_trash_profiles,
)
from charmarr_lib.core.interfaces import (
    CrowsnestProvider,
    CrowsnestProviderData,
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
        self._scraparr_container = self.unit.get_container(METRICS_CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._topology = CharmarrChargedTopology(
            self,
            relations=[
                CharmarrTopologyRelation("download-client", role="requires", required=True),
                CharmarrTopologyRelation("media-indexer", role="requires", required=True),
                CharmarrTopologyRelation("media-storage", role="requires", required=True),
                CharmarrTopologyRelation("vpn-gateway", role="requires", required=False),
                CharmarrTopologyRelation("media-manager", role="provides", required=False),
            ],
            extra_exposition=self._build_queue_gauges,
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
            refresh_event=[self.on.scraparr_pebble_ready],
        )
        self._grafana_dashboards = GrafanaDashboardProvider(self)
        self._log_forwarder = LogForwarder(self, relation_name="logging")
        self._charm_tracing = ops.tracing.Tracing(self, tracing_relation_name="charm-tracing")

        self._media_manager = MediaManagerProvider(self, "media-manager")
        self._media_indexer = MediaIndexerRequirer(self, "media-indexer")
        self._download_client = DownloadClientRequirer(self, "download-client")
        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")
        self._crowsnest = CrowsnestProvider(self, "crowsnest")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="media-manager",
                    endpoints=[Endpoint(ports=[WEBUI_PORT])],
                ),
                AppPolicy(
                    relation="media-indexer",
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
        framework.observe(self._vpn_gateway.on.changed, self._reconcile)
        framework.observe(self._media_indexer.on.changed, self._reconcile)
        framework.observe(self._download_client.on.changed, self._reconcile)
        framework.observe(self._media_storage.on.changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
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
        url_base = str(self.config["ingress-path"]) or f"/{self.app.name}"
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
                        # Sonarr reads url_base from config.xml, not env, but including
                        # it here ensures Pebble restarts service when ingress-path changes
                        "__CHARM_URL_BASE": self._get_url_base() or "",
                    },
                }
            },
            "checks": self._build_readiness_check(),
        }

    def _build_scraparr_layer(self, api_key: str) -> ops.pebble.LayerDict:
        return {
            "summary": "scraparr Prometheus exporter",
            "services": {
                METRICS_SERVICE_NAME: {
                    "override": "replace",
                    "summary": "scraparr exporter for Sonarr",
                    "command": SCRAPARR_COMMAND,
                    "startup": "enabled",
                    "environment": {
                        SCRAPARR_ENV_URL: f"http://localhost:{WEBUI_PORT}",
                        SCRAPARR_ENV_API_KEY: api_key,
                        SCRAPARR_ENV_DETAILED: "true",
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

    def _reconcile_scraparr(self, api_key: str) -> None:
        if not self._scraparr_container.can_connect():
            return
        layer = self._build_scraparr_layer(api_key)
        self._scraparr_container.add_layer(METRICS_SERVICE_NAME, layer, combine=True)
        self._scraparr_container.replan()

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

    def _build_queue_gauges(self) -> list[MetricFamily]:
        """Poll Sonarr's /api/v3/queue and emit one series per queued item.

        Surfaces what's currently in-flight (title, status, protocol) so
        per-charm + crowsnest dashboards can render a live "active downloads"
        table without recreating Sonarr's UI. Silent on workload-not-ready
        or empty queue - topology metrics still ship.
        """
        secret_data = self._get_api_key_secret()
        if not secret_data:
            return []
        api_key, _ = secret_data
        try:
            with self._get_api_client(api_key) as api:
                items = api.get_queue()
        except ArrApiError as e:
            logger.debug("Queue poll failed: %s", e)
            return []

        if not items:
            return []

        size_samples: list[MetricSample] = []
        remaining_samples: list[MetricSample] = []
        for item in items:
            labels = {
                "title": item.title,
                "status": item.status,
                "protocol": item.protocol,
            }
            size_samples.append(MetricSample(labels=labels, value=float(item.size)))
            remaining_samples.append(MetricSample(labels=labels, value=float(item.sizeleft)))

        return [
            MetricFamily(
                name="charmarr_queue_item_size_bytes",
                help="Total size in bytes of a currently queued media item.",
                samples=size_samples,
            ),
            MetricFamily(
                name="charmarr_queue_item_remaining_bytes",
                help="Bytes remaining to download for a currently queued media item.",
                samples=remaining_samples,
            ),
        ]

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

    def _get_variant(self) -> ContentVariant:
        """Get content variant from config."""
        value = str(self.config.get("variant", "standard"))
        try:
            return ContentVariant(value)
        except ValueError:
            return ContentVariant.STANDARD

    def _get_root_folder_path(self) -> str:
        """Get root folder path based on variant config."""
        return get_root_folder(self._get_variant(), MediaManager.SONARR)

    def _reconcile_root_folder(self, api_key: str, puid: int, pgid: int) -> None:
        """Ensure root folder exists in Sonarr."""
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
        profiles_config = str(self.config.get("trash-profiles", "")).strip()
        if not profiles_config:
            profiles_config = get_default_trash_profiles(self._get_variant())
        if not profiles_config:
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
        variant_root_folder = self._get_root_folder_path()

        data = MediaManagerProviderData(
            api_url=self._internal_url,
            api_key_secret_id=secret_id,
            manager=MediaManager.SONARR,
            instance_name=self.app.name,
            base_path=self._get_url_base(),
            quality_profiles=quality_profiles,
            root_folders=[variant_root_folder],
            variant=self._get_variant(),
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
        self._reconcile_scraparr(new_api_key)

    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Refresh topology metrics + ensure topology daemon is running
        2. Non-leader: register readiness check (for K8s probe) and exit
        3. Submit ingress route config (if ingress relation exists)
        4. Wait for Pebble connection
        5. Ensure API key exists in Juju secret
        6. Write config file if missing or API key mismatch
        7. Reconcile VPN gateway client (if related)
        8. Configure Pebble layer and start service
        9. Once workload ready:
           - Sync Trash Guides profiles via Recyclarr (if configured)
           - Reconcile download clients from relations
           - Reconcile root folder from config
           - Publish media-manager data to related apps
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

        self._configure_ingress()

        if not self._container.can_connect():
            return

        storage = self._media_storage.get_provider()
        if not storage:
            return

        # Ensure API key exists (charm creates it, not the app)
        secret_data = self._get_api_key_secret()
        if secret_data:
            api_key, secret_id = secret_data
            secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
            sync_secret_rotation_policy(
                secret, str(self.config.get("api-key-rotation", "disabled"))
            )
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

        # Reconcile scraparr sidecar (Prometheus exporter)
        self._reconcile_scraparr(api_key)

        self.unit.set_ports(WEBUI_PORT, self._topology.port)

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

        self._reconcile_scraparr(new_api_key)

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
        profiles_config = str(self.config.get("trash-profiles", "")).strip()
        if not profiles_config:
            profiles_config = get_default_trash_profiles(self._get_variant())
        if not profiles_config:
            event.fail("No trash-profiles configured and no default for standard variant")
            return

        try:
            self._sync_trash_profiles(api_key)
            event.set_results({"result": "Trash profiles synced successfully"})
        except RecyclarrError as e:
            event.fail(f"Recyclarr sync failed: {e}")


if __name__ == "__main__":
    ops.main(SonarrCharm)
