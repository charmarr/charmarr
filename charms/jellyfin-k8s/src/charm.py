#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Jellyfin Media Server Charm."""

import logging
import secrets

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
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from charms.velero_libs.v0.velero_backup_config import VeleroBackupProvider, VeleroBackupSpec

from _jellyfin import (
    ADMIN_SECRET_LABEL,
    ADMIN_USERNAME,
    API_KEY_APP_NAME,
    API_KEY_SECRET_LABEL,
    CACHE_DIR,
    CONFIG_DIR,
    CONTAINER_NAME,
    DATA_DIR,
    FFMPEG_PATH,
    JELLYFIN_BINARY,
    LOG_DIR,
    METRICS_PATH,
    METRICS_PORT,
    SERVICE_NAME,
    SYSTEM_XML,
    WEB_DIR,
    WEBUI_PORT,
    JellyfinApi,
    JellyfinApiError,
    collection_type,
    enable_metrics,
    is_startup_wizard_completed,
    library_name,
)
from charmarr_lib.core import (
    CharmarrTopology,
    CharmarrTopologyRelation,
    K8sResourceManager,
    ensure_pebble_user,
    observe_events,
    reconcilable_events_k8s,
    reconcile_hardware_transcoding,
    reconcile_storage_volume,
)
from charmarr_lib.core.interfaces import (
    CrowsnestProvider,
    CrowsnestProviderData,
    MediaManagerRequirer,
    MediaServerProvider,
    MediaServerProviderData,
    MediaStorageRequirer,
)

logger = logging.getLogger(__name__)


class JellyfinCharm(ops.CharmBase):
    """Jellyfin Media Server charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._topology = CharmarrTopology(
            self,
            relations=[
                CharmarrTopologyRelation("media-storage", role="requires", required=True),
                CharmarrTopologyRelation("media-manager", role="requires", required=False),
                CharmarrTopologyRelation("media-server", role="provides", required=False),
            ],
        )
        self._metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[
                {
                    "metrics_path": METRICS_PATH,
                    "static_configs": [{"targets": [f"*:{METRICS_PORT}"]}],
                },
                self._topology.scrape_job,
            ],
            alert_rules_path=(
                "src/prometheus_alert_rules_extended"
                if bool(self.config.get("extended-alert-rules", False))
                else "src/prometheus_alert_rules"
            ),
            refresh_event=[self.on.jellyfin_pebble_ready],
        )
        self._grafana_dashboards = GrafanaDashboardProvider(self)
        self._log_forwarder = LogForwarder(self, relation_name="logging")
        self._charm_tracing = ops.tracing.Tracing(self, tracing_relation_name="charm-tracing")

        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._media_manager = MediaManagerRequirer(self, "media-manager")
        self._media_server = MediaServerProvider(self, "media-server")
        self._crowsnest = CrowsnestProvider(self, "crowsnest")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="media-server",
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
        self._ingress = IngressPerAppRequirer(self, port=WEBUI_PORT, strip_prefix=True)
        self._istio_ingress = IstioIngressRouteRequirer(self, relation_name="istio-ingress-route")
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

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self._media_storage.on.changed, self._reconcile)
        framework.observe(self._media_manager.on.changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self._ingress.on.ready, self._reconcile)
        framework.observe(self._ingress.on.revoked, self._reconcile)

    @property
    def k8s(self) -> K8sResourceManager:
        """Lazily initialize K8s resource manager."""
        if self._k8s is None:
            self._k8s = K8sResourceManager()
        return self._k8s

    def _is_service_running(self) -> bool:
        """Check if Jellyfin service is running."""
        services = self._container.get_services(SERVICE_NAME)
        return bool(services) and services[SERVICE_NAME].is_running()

    def _is_setup_complete(self) -> bool:
        """Check if the Jellyfin startup wizard has been completed.

        A configured server writes IsStartupWizardCompleted=true to system.xml.
        """
        if not self._container.can_connect():
            return False
        try:
            content = self._container.pull(SYSTEM_XML).read()
        except (ops.pebble.PathError, FileNotFoundError):
            return False
        return is_startup_wizard_completed(content)

    @property
    def _internal_url(self) -> str:
        """Internal K8s service URL for Jellyfin."""
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{WEBUI_PORT}"

    @property
    def _localhost_url(self) -> str:
        """Loopback URL used for charm-to-workload API calls."""
        return f"http://localhost:{WEBUI_PORT}"

    def _get_secret_content(self, label: str) -> dict[str, str] | None:
        """Read a charm-owned secret by label, or None if it does not exist."""
        try:
            return self.model.get_secret(label=label).get_content(refresh=True)
        except ops.SecretNotFoundError:
            return None

    def _get_api_key(self) -> str | None:
        """Get the Jellyfin API key minted during bootstrap."""
        content = self._get_secret_content(API_KEY_SECRET_LABEL)
        return content["api-key"] if content else None

    def _store_api_key(self, api_key: str) -> None:
        """Persist the minted API key in a charm-owned secret."""
        self.app.add_secret({"api-key": api_key}, label=API_KEY_SECRET_LABEL)

    def _create_admin_credentials(self) -> dict[str, str]:
        """Generate and persist the admin credentials used to bootstrap Jellyfin."""
        credentials = {"username": ADMIN_USERNAME, "password": secrets.token_urlsafe(24)}
        self.app.add_secret(credentials, label=ADMIN_SECRET_LABEL)
        logger.info("Generated Jellyfin admin credentials for %s", ADMIN_USERNAME)
        return credentials

    def _reconcile_setup(self) -> None:
        """Complete the startup wizard and mint an API key.

        Jellyfin's API key is server-wide and survives password changes, so
        this only ever needs to run once. Credentials are persisted before the
        wizard runs so an interrupted bootstrap can still authenticate on the
        next pass.
        """
        if self._get_api_key():
            return

        try:
            with JellyfinApi(self._localhost_url) as api:
                if not api.is_ready():
                    return

                wizard_completed = api.is_setup_complete()
                credentials = self._get_secret_content(ADMIN_SECRET_LABEL)
                if wizard_completed and not credentials:
                    logger.warning(
                        "Jellyfin was set up outside the charm - cannot mint an API key, "
                        "so libraries will not be managed"
                    )
                    return

                if not credentials:
                    credentials = self._create_admin_credentials()
                if not wizard_completed:
                    api.complete_setup_wizard(credentials["username"], credentials["password"])

                token = api.authenticate(credentials["username"], credentials["password"])
                self._store_api_key(api.ensure_api_key(API_KEY_APP_NAME, token))
        except JellyfinApiError as e:
            logger.warning("Failed to bootstrap Jellyfin: %s", e)

    def _reconcile_libraries(self, api_key: str) -> None:
        """Create Jellyfin libraries for root folders published by Radarr/Sonarr."""
        providers = self._media_manager.get_providers()
        if not providers:
            return

        try:
            with JellyfinApi(self._localhost_url, token=api_key) as api:
                existing = {
                    loc for folder in api.get_virtual_folders() for loc in folder.locations
                }

                for provider in providers:
                    for root_folder in provider.root_folders:
                        if root_folder in existing:
                            continue
                        api.create_virtual_folder(
                            name=library_name(provider.manager, provider.variant),
                            collection_type=collection_type(provider.manager),
                            path=root_folder,
                        )
                        existing.add(root_folder)
        except JellyfinApiError as e:
            logger.warning("Failed to reconcile Jellyfin libraries: %s", e)

    def _build_readiness_check(self) -> dict:
        """Build Pebble readiness check using the /health endpoint."""
        health_url = f"http://localhost:{WEBUI_PORT}/health"
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
        """Build Pebble layer - bypasses s6-overlay, runs Jellyfin binary directly."""
        env: dict[str, str] = {
            "HOME": CONFIG_DIR,
            "JELLYFIN_CONFIG_DIR": CONFIG_DIR,
            "JELLYFIN_DATA_DIR": DATA_DIR,
            "JELLYFIN_CACHE_DIR": CACHE_DIR,
            "JELLYFIN_LOG_DIR": LOG_DIR,
            "JELLYFIN_WEB_DIR": WEB_DIR,
            "TZ": str(self.config.get("timezone", "Etc/UTC")),
        }

        return {
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "command": f"{JELLYFIN_BINARY} --ffmpeg={FFMPEG_PATH}",
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

    def _reconcile_metrics(self, puid: int, pgid: int) -> None:
        """Enable Jellyfin's native Prometheus endpoint in system.xml.

        Jellyfin seeds system.xml on first start with metrics disabled. Flip the
        flag and restart so the /metrics endpoint comes online. Converges: once
        enabled, subsequent reconciles are a no-op.
        """
        try:
            content = self._container.pull(SYSTEM_XML).read()
        except (ops.pebble.PathError, FileNotFoundError):
            return

        updated = enable_metrics(content)
        if updated != content:
            # Pebble writes as root unless told otherwise; Jellyfin must keep
            # ownership of system.xml or it fails startup with a write error.
            self._container.push(SYSTEM_XML, updated, user_id=puid, group_id=pgid)
            logger.info("Enabled Jellyfin native metrics endpoint")
            if self._is_service_running():
                self._container.restart(SERVICE_NAME)

    def _configure_ingress(self) -> None:
        """Submit ingress route config to the istio-ingress gateway."""
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        listener = Listener(port=int(self.config["ingress-port"]), protocol=ProtocolType.HTTP)

        config = IstioIngressRouteConfig(
            model=self.model.name,
            listeners=[listener],
            http_routes=[
                HTTPRoute(
                    name="jellyfin",
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
        self._istio_ingress.submit_config(config)
        logger.info("Submitted ingress route config for Jellyfin")

    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Refresh topology metrics + publish crowsnest endpoint
        2. Non-leader: register readiness check and exit
        3. Submit ingress route config (if ingress relation exists)
        4. Wait for Pebble connection and media-storage relation
        5. Mount shared storage PVC and reconcile hardware transcoding
        6. Configure Pebble layer and start workload
        7. Enable native metrics endpoint
        8. Publish media-server data for request managers (Seerr)
        9. Bootstrap admin + API key, then create libraries from media-manager
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
        self._container.exec(["chown", "-R", f"{storage.puid}:{storage.pgid}", CONFIG_DIR]).wait()

        # Ensure Jellyfin data directories exist with correct ownership
        self._container.exec(
            ["mkdir", "-p", DATA_DIR, CACHE_DIR, LOG_DIR],
            user_id=storage.puid,
            group_id=storage.pgid,
        ).wait()

        # Ensure user/group exist for Pebble's user-id/group-id
        ensure_pebble_user(self._container, storage.puid, storage.pgid, username="jellyfin")

        # Configure Pebble layer and start service
        layer = self._build_pebble_layer(storage.puid, storage.pgid)
        self._container.add_layer(SERVICE_NAME, layer, combine=True)
        self._container.replan()

        # Enable native metrics endpoint (edits system.xml, restarts if changed)
        self._reconcile_metrics(storage.puid, storage.pgid)

        self.unit.set_ports(WEBUI_PORT, self._topology.port)

        # Publish media-server data for request managers (Seerr)
        self._media_server.publish_data(
            MediaServerProviderData(
                name=self.app.name,
                api_url=self._internal_url,
            )
        )

        # Complete the startup wizard and mint an API key, then create libraries
        # for whatever Radarr/Sonarr instances are related.
        self._reconcile_setup()
        if api_key := self._get_api_key():
            self._reconcile_libraries(api_key)

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
        """Report workload status including bootstrap state."""
        if not self.unit.is_leader():
            return
        if not self._container.can_connect():
            return
        if not self._media_storage.is_ready():
            return

        if not self._is_service_running():
            event.add_status(ops.WaitingStatus("Waiting for workload"))
            return

        if self._get_api_key():
            event.add_status(ops.ActiveStatus())
        elif self._is_setup_complete() and not self._get_secret_content(ADMIN_SECRET_LABEL):
            event.add_status(ops.BlockedStatus("Jellyfin was set up outside the charm"))
        else:
            event.add_status(ops.WaitingStatus("Bootstrapping Jellyfin"))


if __name__ == "__main__":
    ops.main(JellyfinCharm)
