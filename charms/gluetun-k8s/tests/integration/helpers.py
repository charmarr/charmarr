# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions specific to gluetun-k8s integration tests."""

import logging
import re
from pathlib import Path
from typing import Any

import jubilant
from pydantic import BaseModel
from pytest_jubilant import pack

from charmarr_lib.testing import get_oci_resources

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


class VXLANInfo(BaseModel):
    """VXLAN interface info returned from check-vxlan-interface action."""

    exists: bool
    ip: str


class ContainerInfo(BaseModel):
    """Container info returned from get-statefulset-containers action."""

    containers: list[str]
    init_containers: list[str]


class NetworkPolicyInfo(BaseModel):
    """NetworkPolicy info returned from check-network-policy action."""

    exists: bool
    egress_cidrs: list[str]


def pack_gluetun_charm() -> Path:
    """Pack the gluetun charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def create_vpn_secret(juju: jubilant.Juju, private_key: str) -> str:
    """Create Juju secret with WireGuard private key. Returns the secret URI."""
    output = juju.cli("add-secret", "vpn-key", f"private-key={private_key}")
    match = re.search(r"(secret:\S+)", output)
    if not match:
        raise RuntimeError(f"Failed to parse secret URI from: {output}")
    return match.group(1)


def grant_secret_to_app(juju: jubilant.Juju, secret_name: str, app: str) -> None:
    """Grant a secret to an application."""
    juju.cli("grant-secret", secret_name, app)


def deploy_gluetun_charm(
    juju: jubilant.Juju,
    charm_path: Path,
    config: dict[str, str],
    secret_uri: str,
) -> None:
    """Deploy gluetun charm with VPN configuration."""
    full_config = {**config, "wireguard-private-key-secret": secret_uri}
    logger.info(
        "Deploying gluetun with config: %s",
        {k: v for k, v in full_config.items() if "key" not in k.lower()},
    )
    juju.deploy(
        str(charm_path),
        app="gluetun",
        trust=True,
        config={k: str(v) for k, v in full_config.items()},
        resources=get_oci_resources(CHARM_DIR),
    )


def _run_multimeter_action(
    juju: jubilant.Juju, action: str, params: dict[str, Any] | None = None
) -> dict[str, str]:
    """Run an action on multimeter and return results. Returns empty dict on failure."""
    try:
        result = juju.run("charmarr-multimeter/0", action, params or {})
        return dict(result.results)
    except Exception as e:
        logger.warning("Action %s failed: %s", action, e)
        return {}


def get_external_ip(juju: jubilant.Juju) -> str | None:
    """Get external IP from multimeter container."""
    results = _run_multimeter_action(juju, "get-external-ip")
    return results.get("ip") or None


def get_vxlan_info(juju: jubilant.Juju) -> VXLANInfo:
    """Get VXLAN interface info from multimeter container."""
    results = _run_multimeter_action(juju, "check-vxlan-interface")
    return VXLANInfo(
        exists=results.get("exists") == "true",
        ip=results.get("ip", ""),
    )


def get_container_info(juju: jubilant.Juju, namespace: str, name: str) -> ContainerInfo:
    """Get container names from a StatefulSet via multimeter action."""
    results = _run_multimeter_action(
        juju, "get-statefulset-containers", {"namespace": namespace, "name": name}
    )
    containers_str = results.get("containers", "")
    init_str = results.get("init-containers", "")
    return ContainerInfo(
        containers=containers_str.split(",") if containers_str else [],
        init_containers=init_str.split(",") if init_str else [],
    )


def get_container_env_var(
    juju: jubilant.Juju, namespace: str, name: str, container: str, var: str
) -> str:
    """Get a single environment variable from a container."""
    results = _run_multimeter_action(
        juju,
        "get-container-env",
        {"namespace": namespace, "name": name, "container": container, "var": var},
    )
    return results.get("value", "")


def get_network_policy_info(juju: jubilant.Juju, namespace: str, name: str) -> NetworkPolicyInfo:
    """Get NetworkPolicy info via multimeter action."""
    results = _run_multimeter_action(
        juju, "check-network-policy", {"namespace": namespace, "name": name}
    )
    cidrs_str = results.get("egress-cidrs", "")
    return NetworkPolicyInfo(
        exists=results.get("exists") == "true",
        egress_cidrs=cidrs_str.split(",") if cidrs_str else [],
    )


def configmap_exists(juju: jubilant.Juju, namespace: str, name: str) -> bool:
    """Check if a ConfigMap exists via multimeter action."""
    results = _run_multimeter_action(
        juju, "check-configmap", {"namespace": namespace, "name": name}
    )
    return results.get("exists") == "true"


def get_gateway_client_config(juju: jubilant.Juju) -> dict[str, str]:
    """Get gateway client config from multimeter's ConfigMap."""
    return _run_multimeter_action(juju, "get-gateway-client-config")


def check_connectivity(juju: jubilant.Juju, target: str, timeout: int = 5) -> bool:
    """Check if multimeter can reach a target via multimeter action."""
    results = _run_multimeter_action(
        juju, "check-connectivity", {"target": target, "timeout": timeout}
    )
    return results.get("reachable") == "true"


def get_gluetun_status(juju: jubilant.Juju) -> tuple[str, str]:
    """Get gluetun charm status and message."""
    status = juju.status()
    app = status.apps.get("gluetun")
    if not app:
        return ("unknown", "App not found")
    return (app.app_status.current, app.app_status.message)


def extract_vpn_ip_from_status(message: str) -> str | None:
    """Extract VPN IP from status message like 'VPN connected (1.2.3.4)'."""
    match = re.search(r"\(([0-9.]+)\)", message)
    return match.group(1) if match else None
