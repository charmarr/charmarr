#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Gluetun VPN Gateway Charm."""

import json
import logging
from typing import Any

import httpx
import ops
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import Container, SecurityContext
from lightkube.resources.apps_v1 import StatefulSet
from ops.pebble import Layer
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from charmarr_lib.core import K8sResourceManager, observe_events, reconcilable_events_k8s
from charmarr_lib.vpn import (
    ISTIO_ZTUNNEL_LINK_LOCAL,
    get_cluster_dns_ip,
    reconcile_gateway,
)
from charmarr_lib.vpn.interfaces import VPNGatewayProvider, VPNGatewayProviderData

GLUETUN_CONTAINER_NAME = "gluetun"
DEFAULT_WIREGUARD_PORT = 51820

logger = logging.getLogger(__name__)

PROVIDERS_REQUIRING_ADDRESSES = frozenset({"mullvad", "custom"})
GLUETUN_HTTP_PORT = 8000
PRIVATE_KEY_ATTRIBUTE = "private-key"
GLUETUN_API_TIMEOUT = 5.0
HEALTH_CHECK_RETRIES = 5
HEALTH_CHECK_WAIT_MIN = 2
HEALTH_CHECK_WAIT_MAX = 5


class VPNHealthStatus(BaseModel, frozen=True):
    """VPN health check result."""

    connected: bool
    external_ip: str | None = None
    error: str | None = None


class GluetunCharm(ops.CharmBase):
    """Gluetun VPN gateway charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(GLUETUN_CONTAINER_NAME)
        self._vpn_gateway = VPNGatewayProvider(self, "vpn-gateway")
        self._k8s: K8sResourceManager | None = None

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    @property
    def k8s(self) -> K8sResourceManager:
        """Lazily initialize K8s resource manager."""
        if self._k8s is None:
            self._k8s = K8sResourceManager()
        return self._k8s

    def _get_config_str(self, key: str, default: str = "", *, lowercase: bool = False) -> str:
        """Get a config value as a stripped string."""
        value = str(self.config.get(key, default)).strip()
        return value.lower() if lowercase else value

    def _get_custom_overrides(self) -> dict[str, str]:
        """Parse custom-overrides config into a dict.

        Returns:
            Parsed environment overrides, or empty dict if unset.

        Raises:
            json.JSONDecodeError: If the config value is not valid JSON.
            ValueError: If the parsed value is not a JSON object.
        """
        raw = self._get_config_str("custom-overrides")
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("custom-overrides must be a JSON object")
        return {str(k): str(v) for k, v in parsed.items()}

    @property
    def _override_mode(self) -> bool:
        """Check if custom overrides are active."""
        return bool(self._get_config_str("custom-overrides"))

    def _validate_vpn_type(self) -> str | None:
        """Validate VPN type is WireGuard."""
        vpn_type = self._get_config_str("vpn-type", "wireguard", lowercase=True)
        if vpn_type != "wireguard":
            return "OpenVPN is not supported"
        return None

    def _validate_required_config(self) -> str | None:
        """Validate required configuration fields are present."""
        if not self._get_config_str("cluster-cidrs"):
            return "cluster-cidrs config is required"
        if not self._get_config_str("vpn-provider"):
            return "vpn-provider config is required"
        if not self.config.get("wireguard-private-key-secret"):
            return "wireguard-private-key-secret is required"
        return None

    def _validate_provider_config(self) -> str | None:
        """Validate provider-specific configuration."""
        provider = self._get_config_str("vpn-provider", lowercase=True)

        if provider in PROVIDERS_REQUIRING_ADDRESSES and not self._get_config_str(
            "wireguard-addresses"
        ):
            return f"wireguard-addresses is required for provider '{provider}'"

        if provider == "custom":
            if not self._get_config_str("vpn-endpoint-ip"):
                return "vpn-endpoint-ip is required for custom provider"
            if not self._get_config_str("wireguard-public-key"):
                return "wireguard-public-key is required for custom provider"

        return None

    def _validate_custom_overrides(self) -> str | None:
        """Validate custom-overrides JSON is parseable."""
        try:
            self._get_custom_overrides()
        except (json.JSONDecodeError, ValueError) as e:
            return f"custom-overrides: {e}"
        return None

    def _validate_override_config(self) -> str | None:
        """Validate config in override mode (relaxed)."""
        if err := self._validate_custom_overrides():
            return err
        if not self._get_config_str("cluster-cidrs"):
            return "cluster-cidrs config is required"
        return None

    def _validate_config(self) -> str | None:
        """Validate charm configuration.

        Returns:
            Error message if config is invalid, None if valid.
        """
        if self._override_mode:
            return self._validate_override_config()
        return (
            self._validate_vpn_type()
            or self._validate_required_config()
            or self._validate_provider_config()
        )

    def _get_private_key(self) -> str | None:
        """Retrieve WireGuard private key from Juju secret."""
        secret_id = self.config.get("wireguard-private-key-secret")
        if not secret_id:
            return None

        try:
            secret = self.model.get_secret(id=str(secret_id))
            content = secret.get_content(refresh=True)
            return content.get(PRIVATE_KEY_ATTRIBUTE)
        except (ops.SecretNotFoundError, ops.ModelError):
            return None

    def _get_cluster_cidrs_list(self) -> list[str]:
        """Parse cluster-cidrs config into a list."""
        cluster_cidrs = self._get_config_str("cluster-cidrs")
        return [c.strip() for c in cluster_cidrs.split(",") if c.strip()]

    def _push_iptables_post_rules(self) -> None:
        """Push iptables INPUT rules to gluetun container.

        Gluetun supports custom iptables rules via /iptables/post-rules.txt.
        These rules allow INPUT traffic from cluster networks (pod, service, node)
        which is required for Juju/Pebble health probes and VXLAN traffic.

        See: https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/firewall.md
        """
        cidrs = self._get_cluster_cidrs_list()
        rules = "\n".join(f"iptables -I INPUT -s {cidr} -j ACCEPT" for cidr in cidrs)
        self._container.push("/iptables/post-rules.txt", rules, make_dirs=True)

    def _build_readiness_check(self) -> dict:
        """Build readiness check definition for Pebble layer."""
        return {
            f"{GLUETUN_CONTAINER_NAME}-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": f"http://localhost:{GLUETUN_HTTP_PORT}/v1/publicip/ip"},
                "period": "10s",
                "timeout": "3s",
                "threshold": 3,
            }
        }

    def _build_pebble_layer(self, private_key: str | None = None) -> Layer:
        """Build Pebble layer for gluetun service."""
        provider = self._get_config_str("vpn-provider", lowercase=True)
        cluster_cidrs = self._get_config_str("cluster-cidrs")
        dns_over_tls = self.config.get("dns-over-tls", False)

        env: dict[str, str] = {
            "VPN_SERVICE_PROVIDER": provider,
            "VPN_BLOCK_OTHER_TRAFFIC": "true",
            "FIREWALL_OUTBOUND_SUBNETS": cluster_cidrs,
            "DOT": "on" if dns_over_tls else "off",
        }

        if private_key:
            env["VPN_TYPE"] = "wireguard"
            env["WIREGUARD_PRIVATE_KEY"] = private_key

            if addr := self._get_config_str("wireguard-addresses"):
                env["WIREGUARD_ADDRESSES"] = addr

            if provider == "custom":
                env["VPN_ENDPOINT_IP"] = self._get_config_str("vpn-endpoint-ip")
                env["VPN_ENDPOINT_PORT"] = str(
                    self.config.get("vpn-endpoint-port", DEFAULT_WIREGUARD_PORT)
                )
                env["WIREGUARD_PUBLIC_KEY"] = self._get_config_str("wireguard-public-key")

        if countries := self._get_config_str("server-countries"):
            env["SERVER_COUNTRIES"] = countries
        if cities := self._get_config_str("server-cities"):
            env["SERVER_CITIES"] = cities

        env.update(self._get_custom_overrides())

        return Layer(
            {
                "services": {
                    "gluetun": {
                        "override": "replace",
                        "command": "/gluetun-entrypoint",
                        "startup": "enabled",
                        "environment": env,
                    }
                },
                "checks": self._build_readiness_check(),
            }
        )

    @retry(
        stop=stop_after_attempt(HEALTH_CHECK_RETRIES),
        wait=wait_exponential(min=HEALTH_CHECK_WAIT_MIN, max=HEALTH_CHECK_WAIT_MAX),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException, ValueError)),
        reraise=True,
    )
    def _fetch_public_ip(self) -> str:
        """Fetch public IP from gluetun API with retries."""
        with httpx.Client(timeout=GLUETUN_API_TIMEOUT) as client:
            response = client.get(f"http://localhost:{GLUETUN_HTTP_PORT}/v1/publicip/ip")
            response.raise_for_status()
            data = response.json()
            public_ip = data.get("public_ip")
            if not public_ip:
                raise ValueError("No public IP in response")
            return public_ip

    def _check_vpn_health(self) -> VPNHealthStatus:
        """Check VPN connection status via gluetun API."""
        try:
            public_ip = self._fetch_public_ip()
            return VPNHealthStatus(connected=True, external_ip=public_ip)
        except httpx.ConnectError:
            return VPNHealthStatus(connected=False, error="Gluetun API not reachable")
        except httpx.TimeoutException:
            return VPNHealthStatus(connected=False, error="Gluetun API timeout")
        except httpx.HTTPStatusError as e:
            return VPNHealthStatus(connected=False, error=f"HTTP {e.response.status_code}")
        except (httpx.HTTPError, ValueError) as e:
            return VPNHealthStatus(connected=False, error=str(e))

    def _is_gluetun_privileged(self) -> bool:
        """Check if gluetun container has privileged security context."""
        try:
            sts = self.k8s.get(StatefulSet, self.app.name, self.model.name)
        except ApiError:
            return False

        if sts.spec is None or sts.spec.template.spec is None:
            return False

        for container in sts.spec.template.spec.containers or []:
            if (
                container.name == GLUETUN_CONTAINER_NAME
                and container.securityContext
                and container.securityContext.privileged
            ):
                return True
        return False

    def _ensure_gluetun_privileged(self) -> bool:
        """Ensure gluetun container has privileged security context.

        Returns:
            True if patch was applied (pod will restart), False if already privileged.
        """
        if self._is_gluetun_privileged():
            return False

        container = Container(
            name=GLUETUN_CONTAINER_NAME,
            securityContext=SecurityContext(privileged=True),
        )
        patch: dict[str, Any] = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [container.to_dict()],
                    }
                }
            }
        }
        self.k8s.patch(StatefulSet, self.app.name, patch, self.model.name)
        logger.info("Patched gluetun container to privileged mode")
        return True

    def _build_provider_data(
        self, health: VPNHealthStatus, cluster_dns_ip: str
    ) -> VPNGatewayProviderData:
        """Build VPN gateway provider data for relation."""
        # Include ztunnel IP so clients in Istio ambient mesh can respond to probes.
        # Harmless even without Istio since link-local addresses are reserved (RFC 3927).
        cluster_cidrs = f"{self._get_config_str('cluster-cidrs')},{ISTIO_ZTUNNEL_LINK_LOCAL}"
        vxlan_id = int(self.config.get("vxlan-id", 42))

        return VPNGatewayProviderData(
            gateway_dns_name=f"{self.app.name}-endpoints.{self.model.name}.svc.cluster.local",
            vxlan_id=vxlan_id,
            cluster_cidrs=cluster_cidrs,
            cluster_dns_ip=cluster_dns_ip,
            vpn_connected=health.connected,
            external_ip=health.external_ip,
            instance_name=self.app.name,
        )

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile charm state with desired configuration.

        Reconciliation steps:
        1. Non-leader: register readiness check (for K8s probe) and exit
        2. Validate charm config (returns error string if invalid)
        3. Ensure container is privileged (patches StatefulSet, pod restarts)
        4. Wait for Pebble connection
        5. Retrieve WireGuard private key from Juju secret
        6. Push iptables rules and configure Pebble layer
        7. Check VPN health and publish provider data
        """
        # NOTE: charmarr v1 does not support scaling.
        # Non-leader: register readiness check so K8s removes them from Service endpoints.
        # This acts as a guardrail if someone scales the application beyond 1.
        if not self.unit.is_leader():
            if self._container.can_connect():
                self._container.add_layer(
                    f"{GLUETUN_CONTAINER_NAME}-check",
                    Layer({"checks": self._build_readiness_check()}),
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

        # Returns error string if invalid, None if valid
        if config_error := self._validate_config():
            logger.debug("Config validation failed: %s", config_error)
            return

        if self._override_mode:
            logger.warning("Override mode: config validation bypassed, gluetun may misbehave")

        # Returns True if patch applied (pod restarting), False if already privileged
        if self._ensure_gluetun_privileged():
            return

        if not self._container.can_connect():
            return

        private_key = self._get_private_key()
        if not private_key and not self._override_mode:
            return

        # Configure Pebble layer and start service
        self._push_iptables_post_rules()
        layer = self._build_pebble_layer(private_key)
        self._container.add_layer("gluetun", layer, combine=True)
        self._container.replan()

        # Check VPN status and publish to relations
        health = self._check_vpn_health()
        cluster_dns_ip = get_cluster_dns_ip(self.k8s)
        provider_data = self._build_provider_data(health, cluster_dns_ip)
        reconcile_gateway(
            manager=self.k8s,
            statefulset_name=self.app.name,
            namespace=self.model.name,
            data=provider_data,
            input_cidrs=[],  # gluetun handles INPUT rules via post-rules.txt
        )
        self._vpn_gateway.publish_data(provider_data)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses without early returns.

        The framework picks the worst status; collecting all helps debugging.
        """
        self._collect_scaling_status(event)
        self._collect_leader_status(event)
        self._collect_pebble_status(event)
        self._collect_config_status(event)
        self._collect_secret_status(event)
        self._collect_vpn_status(event)

    def _collect_scaling_status(self, event: ops.CollectStatusEvent) -> None:
        """Block non-leader units when scaled beyond 1."""
        if self.app.planned_units() > 1 and not self.unit.is_leader():
            event.add_status(
                ops.BlockedStatus("Scaling not supported - only leader runs workload")
            )

    def _collect_leader_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for non-leader units."""
        if not self.unit.is_leader():
            event.add_status(ops.WaitingStatus("Standby (non-leader unit)"))

    def _collect_pebble_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for Pebble connectivity."""
        if not self._container.can_connect():
            event.add_status(ops.WaitingStatus("Waiting for Pebble"))

    def _collect_config_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for configuration validation."""
        if error := self._validate_config():
            event.add_status(ops.BlockedStatus(error))

    def _collect_secret_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for secret access."""
        if self._validate_config():
            return
        if self._override_mode:
            return
        if not self._get_private_key():
            event.add_status(ops.BlockedStatus("Secret not found or missing private-key"))

    def _collect_vpn_status(self, event: ops.CollectStatusEvent) -> None:
        """Add status for VPN connection."""
        if not self.unit.is_leader():
            return
        if not self._container.can_connect():
            return
        if self._validate_config():
            return
        if not self._get_private_key() and not self._override_mode:
            return

        health = self._check_vpn_health()
        if health.connected:
            event.add_status(ops.ActiveStatus(f"VPN connected ({health.external_ip})"))
        else:
            event.add_status(ops.WaitingStatus("VPN not connected"))


if __name__ == "__main__":
    ops.main(GluetunCharm)
