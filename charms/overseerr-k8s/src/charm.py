#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Overseerr Charm."""

import json
import logging
from collections.abc import Callable
from urllib.parse import urlparse

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
from charms.velero_libs.v0.velero_backup_config import VeleroBackupProvider, VeleroBackupSpec

from _overseerr import (
    API_KEY_SECRET_LABEL,
    CONTAINER_NAME,
    DEFAULT_PGID,
    DEFAULT_PUID,
    SERVICE_NAME,
    SETTINGS_FILE,
    WEBUI_PORT,
    OverseerrApi,
    OverseerrApiError,
)
from charmarr_lib.core import (
    ContentVariant,
    MediaManager,
    RequestManager,
    ensure_pebble_user,
    generate_api_key,
    observe_events,
    reconcilable_events_k8s,
)
from charmarr_lib.core.interfaces import (
    MediaManagerProviderData,
    MediaManagerRequirer,
    MediaManagerRequirerData,
    MediaServerRequirer,
)

logger = logging.getLogger(__name__)


class OverseerrCharm(ops.CharmBase):
    """Overseerr content request management charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)

        self._media_manager = MediaManagerRequirer(self, "media-manager")
        self._media_server = MediaServerRequirer(self, "media-server")
        self._service_mesh = ServiceMeshConsumer(self)
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
        framework.observe(self._media_manager.on.changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self._ingress.on.ready, self._configure_ingress)
        framework.observe(self.on.rotate_api_key_action, self._on_rotate_api_key_action)

    def _get_api_key(self) -> str | None:
        """Read API key from settings.json."""
        if not self._container.can_connect():
            return None

        try:
            content = self._container.pull(SETTINGS_FILE).read()
            settings = json.loads(content)
            return settings.get("main", {}).get("apiKey")
        except (ops.pebble.PathError, json.JSONDecodeError):
            return None

    def _get_secret_id(self, secret: ops.Secret) -> str:
        """Get secret ID reliably (handles ops 2.x quirk with labeled secrets)."""
        return secret.id or secret.get_info().id

    def _ensure_api_key_secret(self, api_key: str) -> str:
        """Ensure API key is stored in Juju secret, return secret ID."""
        try:
            secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
            stored = secret.get_content(refresh=True)["api-key"]
            if stored != api_key:
                secret.set_content({"api-key": api_key})
                logger.info("Updated API key secret (drift detected)")
            return self._get_secret_id(secret)
        except ops.SecretNotFoundError:
            secret = self.app.add_secret(
                {"api-key": api_key},
                label=API_KEY_SECRET_LABEL,
                description="Overseerr API key",
            )
            logger.info("Created API key secret")
            return self._get_secret_id(secret)

    def _is_service_running(self) -> bool:
        """Check if Overseerr service is running."""
        services = self._container.get_services(SERVICE_NAME)
        return bool(services) and services[SERVICE_NAME].is_running()

    def _get_api_client(self, api_key: str) -> OverseerrApi:
        """Create authenticated API client for Overseerr."""
        return OverseerrApi(f"http://localhost:{WEBUI_PORT}", api_key)

    def _is_workload_ready(self, api_key: str) -> bool:
        """Check if Overseerr workload is ready to accept API calls."""
        try:
            with self._get_api_client(api_key) as api:
                api.get_status()
                return True
        except OverseerrApiError:
            return False

    def _build_readiness_check(self) -> dict:
        """Build Pebble readiness check."""
        return {
            f"{CONTAINER_NAME}-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": f"http://localhost:{WEBUI_PORT}/api/v1/status"},
                "period": "10s",
                "timeout": "5s",
                "threshold": 3,
            }
        }

    def _build_pebble_layer(self) -> ops.pebble.LayerDict:
        """Build Pebble layer - bypasses s6-overlay, runs Overseerr directly."""
        log_level = str(self.config.get("log-level", "info")).upper()

        return {
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "command": "/usr/bin/node dist/index.js",
                    "startup": "enabled",
                    "user-id": DEFAULT_PUID,
                    "group-id": DEFAULT_PGID,
                    "working-dir": "/app/overseerr",
                    "environment": {
                        "HOME": "/config",
                        "TZ": "Etc/UTC",
                        "LOG_LEVEL": log_level,
                        "NODE_ENV": "production",
                    },
                }
            },
            "checks": self._build_readiness_check(),
        }

    def _parse_url(self, api_url: str) -> tuple[str, int, bool]:
        """Parse API URL into hostname, port, and SSL flag."""
        parsed = urlparse(api_url)
        hostname = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        use_ssl = parsed.scheme == "https"
        return hostname, port, use_ssl

    def _get_provider_api_key(self, secret_id: str) -> str | None:  # pragma: no cover
        """Retrieve API key from provider's Juju secret."""
        try:
            secret = self.model.get_secret(id=secret_id)
            return secret.get_content(refresh=True).get("api-key")
        except ops.SecretNotFoundError:
            return None

    def _build_server_config(  # pragma: no cover
        self,
        provider: MediaManagerProviderData,
        existing: dict | None,
        all_servers: list[dict],
    ) -> dict | None:
        """Build server configuration for Radarr/Sonarr."""
        provider_api_key = self._get_provider_api_key(provider.api_key_secret_id)
        if not provider_api_key:
            logger.warning("Could not retrieve API key for %s", provider.instance_name)
            return None

        is_4k = provider.variant == ContentVariant.UHD
        is_anime = provider.variant == ContentVariant.ANIME

        has_default_for_tier = any(
            s.get("isDefault") and s.get("is4k") == is_4k
            for s in all_servers
            if s["name"] != provider.instance_name
        )

        hostname, port, use_ssl = self._parse_url(provider.api_url)
        default_profile = provider.quality_profiles[0] if provider.quality_profiles else None

        def preserve_or_default(key: str, default):
            """Use existing value if updating, otherwise use default."""
            return existing.get(key, default) if existing else default

        config = {
            # Managed by relation (always reconciled)
            "name": provider.instance_name,
            "hostname": hostname,
            "port": port,
            "apiKey": provider_api_key,
            "useSsl": use_ssl,
            "is4k": is_4k,
            "isAnime": is_anime,
            "activeDirectory": provider.root_folders[0] if provider.root_folders else "",
            # User-configurable (preserved on update)
            "activeProfileId": preserve_or_default(
                "activeProfileId", default_profile.id if default_profile else None
            ),
            "activeProfileName": preserve_or_default(
                "activeProfileName", default_profile.name if default_profile else ""
            ),
            "minimumAvailability": preserve_or_default("minimumAvailability", "released"),
            "isDefault": preserve_or_default("isDefault", not has_default_for_tier),
            "enableScan": preserve_or_default("enableScan", True),
            "enableAutomaticSearch": preserve_or_default("enableAutomaticSearch", True),
            "externalUrl": preserve_or_default("externalUrl", ""),
        }

        if provider.base_path:
            config["baseUrl"] = provider.base_path

        # Sonarr-specific fields
        if provider.manager == MediaManager.SONARR:
            config["enableSeasonFolders"] = preserve_or_default("enableSeasonFolders", True)

        return config

    def _server_config_matches(self, existing: dict, desired: dict) -> bool:
        """Check if existing server config matches desired config."""
        return all(existing.get(key) == value for key, value in desired.items())

    def _reconcile_servers(  # pragma: no cover
        self,
        api: OverseerrApi,
        manager_type: MediaManager,
        get_servers: Callable[[], list[dict]],
        add_server: Callable[[dict], dict],
        update_server: Callable[[int, dict], dict],
        delete_server: Callable[[int], None],
    ) -> None:
        """Reconcile servers for a media manager type using aggressive deletion.

        Implements declarative reconciliation where Juju relations are the single
        source of truth. Servers configured manually in Overseerr UI that are not
        backed by a Juju relation will be deleted.

        Steps:
        1. Get desired state from media-manager relations
        2. Delete any server in Overseerr not in desired state
        3. Add or update servers to match relation data (skip if unchanged)
        """
        manager_name = manager_type.value

        providers = [p for p in self._media_manager.get_providers() if p.manager == manager_type]
        desired_names = {p.instance_name for p in providers}

        current_servers = get_servers()

        for server in current_servers:
            if server["name"] not in desired_names:
                logger.info("Removing %s server: %s", manager_name, server["name"])
                try:
                    delete_server(server["id"])
                except OverseerrApiError as e:
                    logger.warning(
                        "Failed to delete %s server %s: %s", manager_name, server["name"], e
                    )

        current_servers = get_servers()
        current_by_name = {s["name"]: s for s in current_servers}

        for provider in providers:
            existing = current_by_name.get(provider.instance_name)
            config = self._build_server_config(provider, existing, current_servers)
            if not config:
                continue

            if existing:
                if self._server_config_matches(existing, config):
                    logger.debug(
                        "%s server %s already up to date", manager_name, provider.instance_name
                    )
                    continue
                try:
                    update_server(existing["id"], config)
                    logger.info("Updated %s server: %s", manager_name, provider.instance_name)
                except OverseerrApiError as e:
                    logger.warning(
                        "Failed to update %s server %s: %s",
                        manager_name,
                        provider.instance_name,
                        e,
                    )
            else:
                try:
                    add_server(config)
                    logger.info("Added %s server: %s", manager_name, provider.instance_name)
                except OverseerrApiError as e:
                    logger.warning(
                        "Failed to add %s server %s: %s", manager_name, provider.instance_name, e
                    )

    def _ensure_server_defaults(  # pragma: no cover
        self,
        manager_name: str,
        get_servers: Callable[[], list[dict]],
        update_server: Callable[[int, dict], dict],
    ) -> None:
        """Ensure at least one default server exists for each tier (4K and non-4K).

        After removing servers, the remaining servers may have no default set.
        This promotes the first server in each tier to default if none exists.
        """
        servers = get_servers()
        non_4k = [s for s in servers if not s.get("is4k")]
        is_4k = [s for s in servers if s.get("is4k")]

        # Fields accepted by the Overseerr API for server updates
        allowed_fields = {
            "name",
            "hostname",
            "port",
            "apiKey",
            "useSsl",
            "is4k",
            "isAnime",
            "isDefault",
            "activeProfileId",
            "activeProfileName",
            "activeDirectory",
            "minimumAvailability",
            "enableScan",
            "enableAutomaticSearch",
            "externalUrl",
            "baseUrl",
            "enableSeasonFolders",
        }

        for tier_name, tier_servers in [("non-4K", non_4k), ("4K", is_4k)]:
            if tier_servers and not any(s.get("isDefault") for s in tier_servers):
                first = tier_servers[0]
                try:
                    config = {k: v for k, v in first.items() if k in allowed_fields}
                    config["isDefault"] = True
                    update_server(first["id"], config)
                    logger.info(
                        "Promoted %s %s server '%s' to default",
                        tier_name,
                        manager_name,
                        first["name"],
                    )
                except OverseerrApiError as e:
                    logger.warning(
                        "Failed to set default for %s %s: %s", tier_name, manager_name, e
                    )

    def _reconcile_media_managers(self, api: OverseerrApi) -> None:  # pragma: no cover
        """Reconcile all media manager servers (Radarr and Sonarr)."""
        self._reconcile_servers(
            api,
            MediaManager.RADARR,
            api.get_radarr_servers,
            api.add_radarr_server,
            api.update_radarr_server,
            api.delete_radarr_server,
        )
        self._reconcile_servers(
            api,
            MediaManager.SONARR,
            api.get_sonarr_servers,
            api.add_sonarr_server,
            api.update_sonarr_server,
            api.delete_sonarr_server,
        )

        self._ensure_server_defaults("Radarr", api.get_radarr_servers, api.update_radarr_server)
        self._ensure_server_defaults("Sonarr", api.get_sonarr_servers, api.update_sonarr_server)

    def _publish_requirer_data(self) -> None:  # pragma: no cover
        """Publish requirer data to media-manager relations."""
        if not self.model.relations.get("media-manager"):
            return

        data = MediaManagerRequirerData(
            requester=RequestManager.OVERSEERR,
            instance_name=self.app.name,
        )
        self._media_manager.publish_data(data)
        logger.info("Published media manager requirer data")

    def _configure_ingress(self, _: ops.EventBase) -> None:  # pragma: no cover
        """Submit ingress route config to istio-ingress gateway.

        Overseerr does not support URL path prefixes - it must be served from root.
        Use a dedicated subdomain (e.g., requests.example.com) via ingress host routing.
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
                    name="overseerr",
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
        logger.info("Submitted ingress route config for Overseerr")

    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Steps:
        1. Non-leader: register readiness check and exit
        2. Wait for Pebble connection
        3. Fix /config ownership and ensure user/group exist
        4. Configure Pebble layer and start service
        5. Publish requirer data to media-manager relations
        6. Wait for API key (created by Overseerr on first start)
        7. Store API key in Juju secret
        8. Reconcile Radarr/Sonarr servers from relations
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

        self._container.exec(["chown", "-R", f"{DEFAULT_PUID}:{DEFAULT_PGID}", "/config"]).wait()

        ensure_pebble_user(self._container, DEFAULT_PUID, DEFAULT_PGID, username="overseerr")

        layer = self._build_pebble_layer()
        self._container.add_layer(SERVICE_NAME, layer, combine=True)
        self._container.replan()

        self.unit.set_ports(WEBUI_PORT)

        self._publish_requirer_data()

        api_key = self._get_api_key()
        if not api_key:
            logger.info("API key not yet available, waiting for Overseerr to start")
            return

        self._ensure_api_key_secret(api_key)

        if not self._is_workload_ready(api_key):
            return

        with self._get_api_client(api_key) as api:
            if api.is_initialized():
                self._reconcile_media_managers(api)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses. Framework picks the worst."""
        self._collect_scaling_status(event)
        self._collect_leader_status(event)
        self._collect_pebble_status(event)
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

    def _collect_workload_status(self, event: ops.CollectStatusEvent) -> None:
        """Report workload status."""
        if not self.unit.is_leader():
            return
        if not self._container.can_connect():
            return

        if not self._is_service_running():
            event.add_status(ops.WaitingStatus("Waiting for workload"))
            return

        api_key = self._get_api_key()
        if not api_key:
            event.add_status(ops.WaitingStatus("Waiting for API key"))
            return

        if not self._is_workload_ready(api_key):
            event.add_status(ops.WaitingStatus("Waiting for workload"))
            return

        with self._get_api_client(api_key) as api:
            if not api.is_initialized():
                event.add_status(ops.WaitingStatus("Complete setup in web UI"))
                return

        event.add_status(ops.ActiveStatus())

    def _on_rotate_api_key_action(self, event: ops.ActionEvent) -> None:
        """Handle rotate-api-key action."""
        if not self.unit.is_leader():
            event.fail("This action can only run on the leader unit")
            return

        if not self._container.can_connect():
            event.fail("Cannot connect to Pebble")
            return

        api_key = self._get_api_key()
        if not api_key:
            event.fail("API key not available")
            return

        new_api_key = generate_api_key()

        try:
            settings_content = self._container.pull(SETTINGS_FILE).read()
            settings = json.loads(settings_content)
            settings.setdefault("main", {})["apiKey"] = new_api_key
            self._container.push(SETTINGS_FILE, json.dumps(settings, indent=2))
        except (ops.pebble.PathError, json.JSONDecodeError) as e:
            event.fail(f"Failed to update settings.json: {e}")
            return

        self._ensure_api_key_secret(new_api_key)

        if self._is_service_running():
            self._container.stop(SERVICE_NAME)
            self._container.start(SERVICE_NAME)
            logger.info("Restarted Overseerr after API key rotation")

        event.set_results({"result": "API key rotated successfully"})


if __name__ == "__main__":
    ops.main(OverseerrCharm)
