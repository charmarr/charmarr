# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions specific to gluetun-k8s integration tests."""

import logging
import re
from pathlib import Path

import jubilant
from pydantic import BaseModel
from pytest_jubilant import pack

from charmarr_lib.testing import get_oci_resources, run_multimeter_action

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


class VXLANInfo(BaseModel):
    """VXLAN interface info returned from check-vxlan-interface action."""

    exists: bool
    ip: str


class NetworkPolicyInfo(BaseModel):
    """NetworkPolicy info returned from check-network-policy action."""

    exists: bool
    egress_cidrs: list[str]


def pack_gluetun_charm() -> Path:
    """Pack the gluetun charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


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


def get_external_ip(juju: jubilant.Juju) -> str | None:
    """Get external IP from multimeter container."""
    results = run_multimeter_action(juju, "get-external-ip")
    return results.get("ip") or None


def get_vxlan_info(juju: jubilant.Juju) -> VXLANInfo:
    """Get VXLAN interface info from multimeter container."""
    results = run_multimeter_action(juju, "check-vxlan-interface")
    return VXLANInfo(
        exists=results.get("exists") == "true",
        ip=results.get("ip", ""),
    )


def get_container_env_var(
    juju: jubilant.Juju, namespace: str, name: str, container: str, var: str
) -> str:
    """Get a single environment variable from a container."""
    results = run_multimeter_action(
        juju,
        "get-container-env",
        {"namespace": namespace, "name": name, "container": container, "var": var},
    )
    return results.get("value", "")


def get_network_policy_info(juju: jubilant.Juju, namespace: str, name: str) -> NetworkPolicyInfo:
    """Get NetworkPolicy info via multimeter action."""
    results = run_multimeter_action(
        juju, "check-network-policy", {"namespace": namespace, "name": name}
    )
    cidrs_str = results.get("egress-cidrs", "")
    return NetworkPolicyInfo(
        exists=results.get("exists") == "true",
        egress_cidrs=cidrs_str.split(",") if cidrs_str else [],
    )


def configmap_exists(juju: jubilant.Juju, namespace: str, name: str) -> bool:
    """Check if a ConfigMap exists via multimeter action."""
    results = run_multimeter_action(
        juju, "check-configmap", {"namespace": namespace, "name": name}
    )
    return results.get("exists") == "true"


def get_gateway_client_config(juju: jubilant.Juju) -> dict[str, str]:
    """Get gateway client config from multimeter's ConfigMap."""
    return run_multimeter_action(juju, "get-gateway-client-config")


def check_connectivity(juju: jubilant.Juju, target: str, timeout: int = 5) -> bool:
    """Check if multimeter can reach a target via multimeter action."""
    results = run_multimeter_action(
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
