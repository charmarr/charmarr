#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Prowlarr Charm."""

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
from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_fixed

from _prowlarr import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    DEFAULT_PGID,
    DEFAULT_PUID,
    SERVICE_NAME,
    WEBUI_PORT,
    FlareSolverrProxyConfig,
    IndexerProxyType,
    ProwlarrApiClient,
)
from charmarr_lib.core import (
    ArrApiResponseError,
    K8sResourceManager,
    MediaIndexer,
    ensure_pebble_user,
    generate_api_key,
    get_secret_rotation_policy,
    observe_events,
    reconcilable_events_k8s,
    reconcile_config_xml,
    reconcile_media_manager_connections,
    sync_secret_rotation_policy,
)
from charmarr_lib.core.interfaces import (
    FlareSolverrRequirer,
    MediaIndexerProvider,
    MediaIndexerProviderData,
)
from charmarr_lib.vpn import reconcile_gateway_client
from charmarr_lib.vpn.interfaces import VPNGatewayRequirer, VPNGatewayRequirerData

logger = logging.getLogger(__name__)


class ProwlarrCharm(ops.CharmBase):
    """Prowlarr indexer manager charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)
        self._k8s: K8sResourceManager | None = None

        self._media_indexer = MediaIndexerProvider(self, "media-indexer")
        self._flaresolverr = FlareSolverrRequirer(self, "flaresolverr")
        self._vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="media-indexer",
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
        framework.observe(self._flaresolverr.on.changed, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self._ingress.on.ready, self._configure_ingress)
        framework.observe(self.on.config_changed, self._configure_ingress)
        framework.observe(self.on.secret_rotate, self._on_secret_rotate)
        framework.observe(self.on.rotate_api_key_action, self._on_rotate_api_key_action)
        framework.observe(self.on.sync_indexers_action, self._on_sync_indexers_action)

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
            description="Prowlarr API key",
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

    def _build_pebble_layer(self) -> ops.pebble.LayerDict:
        """Bypasses s6-overlay, runs Prowlarr directly."""
        return {
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "command": "/app/prowlarr/bin/Prowlarr -nobrowser -data=/config",
                    "startup": "enabled",
                    "user-id": DEFAULT_PUID,
                    "group-id": DEFAULT_PGID,
                    "environment": {
                        "HOME": "/config",
                        "TZ": str(self.config.get("timezone", "Etc/UTC")),
                        # Override TMPDIR - image sets it to /run/prowlarr-temp which
                        # doesn't exist when bypassing s6-overlay; .NET needs it for
                        # atomic writes (e.g., ASP.NET Data Protection keys)
                        "TMPDIR": "/tmp",
                        # Prowlarr reads url_base from config.xml, not env, but including
                        # it here ensures Pebble restarts service when ingress-path changes
                        "__CHARM_URL_BASE": self._get_url_base() or "",
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

    def _get_api_client(self, api_key: str) -> ProwlarrApiClient:
        """Create authenticated API client for Prowlarr."""
        url_base = self._get_url_base() or ""
        base_url = f"http://localhost:{WEBUI_PORT}{url_base}"
        return ProwlarrApiClient(base_url, api_key)

    def _is_workload_ready(self, api_key: str) -> bool:
        """Check if Prowlarr workload is ready to accept API calls."""
        try:
            with self._get_api_client(api_key) as api:
                api.get_host_config()
                return True
        except Exception:
            return False

    def _get_secret_content(self, secret_id: str) -> dict[str, str]:
        """Retrieve secret content by ID for reconcilers."""
        secret = self.model.get_secret(id=secret_id)
        return secret.get_content(refresh=True)

    def _reconcile_media_managers(self, api_key: str, secret_id: str) -> None:
        """Reconcile media manager connections in Prowlarr."""
        requirers = self._media_indexer.get_requirers()
        if not requirers:
            return

        with self._get_api_client(api_key) as api:
            reconcile_media_manager_connections(
                api_client=api,
                desired_managers=requirers,
                indexer_url=self._internal_url,
                get_secret=self._get_secret_content,
            )

    def _configure_flaresolverr_proxy(self, api: ProwlarrApiClient, url: str, tag_id: int) -> None:
        """Configure FlareSolverr proxy in Prowlarr."""
        existing = api.get_indexer_proxies()
        proxy = next(
            (p for p in existing if p.implementation == IndexerProxyType.FLARESOLVERR),
            None,
        )
        if proxy:
            self._update_flaresolverr_proxy_with_fallback(api, proxy.id, url, tag_id)
        else:
            config = FlareSolverrProxyConfig.from_url(url, tags=[tag_id])
            api.add_indexer_proxy(config.model_dump(by_alias=True))
            logger.info("Added FlareSolverr proxy: %s", url)

    def _update_flaresolverr_proxy_with_fallback(
        self, api: ProwlarrApiClient, proxy_id: int, url: str, tag_id: int
    ) -> None:
        """Update FlareSolverr proxy with retry and delete+recreate fallback."""

        def _is_bad_request(exc: BaseException) -> bool:
            return isinstance(exc, ArrApiResponseError) and exc.status_code == 400

        @retry(
            retry=retry_if_exception(_is_bad_request),
            stop=stop_after_attempt(3),
            wait=wait_fixed(2),
        )
        def _try_update() -> None:
            api.update_flaresolverr_host(proxy_id, url, [tag_id])

        try:
            _try_update()
            logger.info("Updated FlareSolverr proxy: %s", url)
        except RetryError as e:
            last_exc = e.last_attempt.exception()
            if last_exc and _is_bad_request(last_exc):
                logger.warning(
                    "FlareSolverr proxy update failed after retries, deleting and recreating"
                )
                api.delete_indexer_proxy(proxy_id)
                config = FlareSolverrProxyConfig.from_url(url, tags=[tag_id])
                api.add_indexer_proxy(config.model_dump(by_alias=True))
                logger.info("Recreated FlareSolverr proxy: %s", url)
            elif last_exc:
                raise last_exc from e
            else:
                raise

    def _reconcile_flaresolverr(self, api_key: str) -> None:
        """Reconcile FlareSolverr proxy based on relation state."""
        flaresolverr_data = self._flaresolverr.get_provider()
        if not flaresolverr_data:
            self._remove_flaresolverr_proxy(api_key)
            return

        if self._service_mesh.mesh_type():
            # Force mesh labels to be applied before configuring FlareSolverr.
            # Labels are normally applied on relation_changed, but relation_created
            # fires first - without labels, Istio blocks traffic to FlareSolverr.
            self._service_mesh._update_labels(None)

        with self._get_api_client(api_key) as api:
            tag = api.get_or_create_tag("flaresolverr")
            try:
                self._configure_flaresolverr_proxy(api, flaresolverr_data.url, tag.id)
            except Exception as e:
                # FlareSolverr may be behind service mesh. If we're not on mesh yet,
                # skip config - it will succeed once mesh relation is established.
                if not self._service_mesh.mesh_type():
                    logger.info("FlareSolverr unreachable, waiting for mesh: %s", e)
                    return
                raise

    def _remove_flaresolverr_proxy(self, api_key: str) -> None:
        """Remove FlareSolverr proxy if it exists."""
        with self._get_api_client(api_key) as api:
            existing = api.get_indexer_proxies()
            proxy = next(
                (p for p in existing if p.implementation == IndexerProxyType.FLARESOLVERR),
                None,
            )
            if proxy:
                api.delete_indexer_proxy(proxy.id)
                logger.info("Removed FlareSolverr proxy (relation removed)")

    def _publish_media_indexer(self, api_key: str, secret_id: str) -> None:
        """Publish media indexer data to all connected media managers."""
        secret = self.model.get_secret(label=API_KEY_SECRET_LABEL)
        for relation in self.model.relations.get("media-indexer", []):
            if relation.app:
                secret.grant(relation)

        data = MediaIndexerProviderData(
            api_url=self._internal_url,
            api_key_secret_id=secret_id,
            indexer=MediaIndexer.PROWLARR,
            base_path=self._get_url_base(),
        )
        self._media_indexer.publish_data(data)
        logger.info("Published media indexer provider data")

    def _configure_ingress(self, _: ops.EventBase) -> None:
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
                    name="prowlarr",
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

    def _reconcile_non_leader(self) -> None:
        """Configure non-leader units with readiness check only.

        Non-leader units do not run the Prowlarr workload but still need
        the readiness check registered for Kubernetes health probes.
        """
        if self._container.can_connect():
            self._container.add_layer(
                f"{CONTAINER_NAME}-check",
                {"checks": self._build_readiness_check()},
                combine=True,
            )

    def _reconcile_pebble_workload(self) -> None:
        """Configure Pebble layer, user setup, and start the workload.

        Handles:
        - Creating the Prowlarr user/group for Pebble's user-id/group-id
        - Fixing /config directory ownership (Juju storage mounts as root)
        - Adding the Pebble layer and replanning the service
        - Exposing the WebUI port on the Kubernetes Service
        """
        ensure_pebble_user(self._container, DEFAULT_PUID, DEFAULT_PGID, username="prowlarr")
        self._container.exec(["chown", "-R", f"{DEFAULT_PUID}:{DEFAULT_PGID}", "/config"]).wait()

        layer = self._build_pebble_layer()
        self._container.add_layer(SERVICE_NAME, layer, combine=True)
        self._container.replan()

        self.unit.set_ports(WEBUI_PORT)

    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Orchestrates the reconciliation process by delegating to focused sub-methods:
        1. Non-leader units: register readiness check and exit early
        2. Leader unit: full reconciliation of workload and integrations
        """
        if not self.unit.is_leader():
            self._reconcile_non_leader()
            return

        if self.app.planned_units() > 1:
            logger.warning(
                "Scaling > 1 not supported. Non-leader units are idle. "
                "Run: juju scale-application %s 1",
                self.app.name,
            )

        if not self._container.can_connect():
            return

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

        self._publish_media_indexer(api_key, secret_id)
        self._reconcile_config(api_key)
        self._reconcile_vpn()
        self._reconcile_pebble_workload()

        if self._is_workload_ready(api_key):
            self._reconcile_flaresolverr(api_key)
            self._reconcile_media_managers(api_key, secret_id)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses. Framework picks the worst."""
        self._collect_scaling_status(event)
        self._collect_leader_status(event)
        self._collect_pebble_status(event)
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

    def _collect_vpn_status(self, event: ops.CollectStatusEvent) -> None:
        gateway = self._vpn_gateway.get_gateway()
        if gateway is not None and not gateway.vpn_connected:
            event.add_status(ops.WaitingStatus("Waiting for VPN connection"))

    def _collect_api_key_status(self, event: ops.CollectStatusEvent) -> None:
        # Early return: only leader creates/manages API key secrets
        if not self.unit.is_leader():
            return
        if not self._get_api_key_secret():
            event.add_status(ops.WaitingStatus("Waiting for API key"))

    def _collect_workload_status(self, event: ops.CollectStatusEvent) -> None:
        # Early return: only leader runs workload
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
            logger.info("Restarted Prowlarr after API key rotation")

        event.set_results({"result": "API key rotated successfully"})

    def _on_sync_indexers_action(self, event: ops.ActionEvent) -> None:
        """Handle sync-indexers action."""
        if not self.unit.is_leader():
            event.fail("This action can only run on the leader unit")
            return

        secret_data = self._get_api_key_secret()
        if not secret_data:
            event.fail("No API key found")
            return

        api_key, secret_id = secret_data
        self._reconcile_media_managers(api_key, secret_id)
        event.set_results({"result": "Indexer sync triggered"})


if __name__ == "__main__":
    ops.main(ProwlarrCharm)
