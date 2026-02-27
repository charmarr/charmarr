#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Plex Media Server Charm."""

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

from _plex import (
    CONTAINER_NAME,
    PLEX_BINARY,
    PLEX_DATA_DIR,
    PREFERENCES_FILE,
    SERVICE_NAME,
    WEBUI_PORT,
    PlexApi,
    PlexApiError,
    ensure_custom_connection,
    exchange_claim_token,
    extract_machine_identifier,
    extract_online_token,
    inject_online_token,
)
from charmarr_lib.core import (
    ContentVariant,
    K8sResourceManager,
    MediaManager,
    ensure_pebble_user,
    observe_events,
    reconcilable_events_k8s,
    reconcile_hardware_transcoding,
    reconcile_storage_volume,
)
from charmarr_lib.core.interfaces import (
    MediaManagerProviderData,
    MediaManagerRequirer,
    MediaServerProvider,
    MediaServerProviderData,
    MediaStorageRequirer,
)

logger = logging.getLogger(__name__)


class PlexCharm(ops.CharmBase):
    """Plex Media Server charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._media_manager = MediaManagerRequirer(self, "media-manager")
        self._media_server = MediaServerProvider(self, "media-server")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="media-server",
                    endpoints=[Endpoint(ports=[WEBUI_PORT])],
                ),
            ],
        )
        self._ingress = IstioIngressRouteRequirer(self, relation_name="istio-ingress-route")
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
        framework.observe(self._ingress.on.ready, self._configure_ingress)
        framework.observe(self.on.force_reclaim_action, self._on_force_reclaim_action)

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

    def _claim_server(self, claim_token: str, force: bool = False) -> tuple[bool, str]:
        """Claim server using the provided claim token.

        Args:
            claim_token: Plex claim token from plex.tv/claim
            force: If True, overwrite existing PlexOnlineToken

        Returns:
            Tuple of (success, message)
        """
        if not self._container.can_connect():
            return False, "Container not ready"

        if self._is_server_claimed() and not force:
            return True, "Server already claimed"

        try:
            content = self._container.pull(PREFERENCES_FILE).read()
        except (ops.pebble.PathError, FileNotFoundError):
            return False, "Preferences.xml not found - wait for Plex to initialize"

        machine_id = extract_machine_identifier(content)
        if not machine_id:
            return False, "ProcessedMachineIdentifier not found - wait for Plex to initialize"

        online_token = exchange_claim_token(claim_token, machine_id)
        if not online_token:
            return False, "Failed to exchange claim token - token may be expired or invalid"

        updated_content = inject_online_token(content, online_token)
        self._container.push(PREFERENCES_FILE, updated_content)
        logger.info("Server claimed successfully")
        return True, "Server claimed successfully"

    def _is_service_running(self) -> bool:
        """Check if Plex service is running."""
        services = self._container.get_services(SERVICE_NAME)
        return bool(services) and services[SERVICE_NAME].is_running()

    @property
    def _internal_url(self) -> str:
        """Internal K8s service URL for Plex."""
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{WEBUI_PORT}"

    def _ensure_internal_url(self) -> None:
        """Ensure internal K8s service URL is in Plex custom connections."""
        try:
            content = self._container.pull(PREFERENCES_FILE).read()
        except (ops.pebble.PathError, FileNotFoundError):
            return

        updated = ensure_custom_connection(content, self._internal_url)
        if updated != content:
            self._container.push(PREFERENCES_FILE, updated)
            logger.info("Added internal URL to custom connections: %s", self._internal_url)

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

    def _get_online_token(self) -> str | None:  # pragma: no cover
        """Get PlexOnlineToken from Preferences.xml for API authentication."""
        try:
            content = self._container.pull(PREFERENCES_FILE).read()
            return extract_online_token(content)
        except (ops.pebble.PathError, FileNotFoundError):
            return None

    def _get_library_name(self, provider: MediaManagerProviderData) -> str:  # pragma: no cover
        """Generate Plex library name based on media manager provider data."""
        base_names = {
            MediaManager.RADARR: "Movies",
            MediaManager.SONARR: "TV Shows",
        }
        base = base_names.get(provider.manager, "Media")

        if provider.variant == ContentVariant.UHD:
            return f"{base} (4K)"
        elif provider.variant == ContentVariant.ANIME:
            if provider.manager == MediaManager.SONARR:
                return "Anime"
            return "Anime Movies"

        return base

    def _get_library_type(self, manager: MediaManager) -> str:  # pragma: no cover
        """Convert MediaManager to Plex library type."""
        if manager == MediaManager.RADARR:
            return "movie"
        elif manager == MediaManager.SONARR:
            return "show"
        return "movie"

    def _reconcile_libraries(self, token: str) -> None:  # pragma: no cover
        """Reconcile Plex libraries based on media-manager relation data."""
        providers = self._media_manager.get_providers()
        if not providers:
            return

        try:
            with PlexApi(f"http://localhost:{WEBUI_PORT}", token) as api:
                if not api.is_server_ready():
                    logger.debug("Plex server not ready for library reconciliation")
                    return

                for provider in providers:
                    for root_folder in provider.root_folders:
                        if api.library_exists_for_path(root_folder):
                            logger.debug("Library already exists for path: %s", root_folder)
                            continue

                        name = self._get_library_name(provider)
                        library_type = self._get_library_type(provider.manager)

                        logger.info(
                            "Creating Plex library '%s' (%s) at %s",
                            name,
                            library_type,
                            root_folder,
                        )
                        api.create_library(name, library_type, root_folder)

        except PlexApiError as e:
            logger.warning("Failed to reconcile Plex libraries: %s", e)

    def _configure_ingress(self, _: ops.EventBase) -> None:
        """Submit ingress route config to istio-ingress gateway.

        Note: Plex does not support URL path prefixes. Use a dedicated ingress.
        """
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

        # Claim server if token configured and server is unclaimed
        claim_token = self._get_claim_token()
        if claim_token:
            self._claim_server(claim_token)

        # Ensure internal URL is in custom connections for service discovery
        self._ensure_internal_url()

        self.unit.set_ports(WEBUI_PORT)

        # Publish media-server data for request managers (Overseerr)
        self._media_server.publish_data(
            MediaServerProviderData(
                name=self.app.name,
                api_url=self._internal_url,
            )
        )

        # Reconcile Plex libraries from media-manager relations (requires claimed server)
        online_token = self._get_online_token()
        if online_token:
            self._reconcile_libraries(online_token)

    def _on_force_reclaim_action(self, event: ops.ActionEvent) -> None:
        """Handle force-reclaim action to reclaim server with new account."""
        claim_token = event.params.get("claim-token", "").strip()
        if not claim_token:
            event.fail("claim-token parameter is required")
            return

        success, message = self._claim_server(claim_token, force=True)
        if not success:
            event.fail(message)

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
        elif self.config.get("claim-token"):
            event.add_status(ops.WaitingStatus("Claiming server"))
        else:
            event.add_status(ops.WaitingStatus("Set claim-token config (plex.tv/claim)"))


if __name__ == "__main__":
    ops.main(PlexCharm)
