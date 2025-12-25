# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for gluetun-k8s integration tests."""

import logging
import os
import subprocess
from pathlib import Path

import jubilant
import pytest

from charmarr_lib.testing import deploy_multimeter, wait_for_active_idle
from tests.integration.helpers import (
    create_vpn_secret,
    deploy_gluetun_charm,
    grant_secret_to_app,
    pack_gluetun_charm,
)

logger = logging.getLogger(__name__)

pytest_plugins = [
    "tests.integration.steps.common_steps",
    "tests.integration.steps.vpn_steps",
    "tests.integration.steps.vxlan_steps",
    "tests.integration.steps.cleanup_steps",
    "tests.integration.steps.istio_steps",
]

POD_CIDR = "10.1.0.0/16"
SERVICE_CIDR = "10.152.183.0/24"


def _vpn_creds_available() -> bool:
    """Check if VPN credentials are available in environment."""
    return bool(os.environ.get("WIREGUARD_PRIVATE_KEY"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark all integration tests as xfail if VPN credentials not available."""
    if _vpn_creds_available():
        return

    xfail_marker = pytest.mark.xfail(
        reason="WIREGUARD_PRIVATE_KEY environment variable required",
        run=False,
    )
    for item in items:
        item.add_marker(xfail_marker)


def _get_node_cidr() -> str:
    """Get node CIDR from environment or discover from Kubernetes.

    Returns a /24 CIDR covering the first node's internal IP.
    """
    if cidr := os.environ.get("NODE_CIDR"):
        return cidr

    result = subprocess.run(
        [
            "kubectl",
            "get",
            "nodes",
            "-o",
            "jsonpath={.items[0].status.addresses[?(@.type=='InternalIP')].address}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    node_ip = result.stdout.strip()
    if not node_ip:
        logger.warning("Could not discover node IP, using 10.0.0.0/8 as fallback")
        return "10.0.0.0/8"

    octets = node_ip.split(".")
    return f"{octets[0]}.{octets[1]}.{octets[2]}.0/24"


@pytest.fixture(scope="module")
def cluster_cidrs() -> str:
    """Build cluster CIDRs string including pod, service, and node networks."""
    node_cidr = _get_node_cidr()
    return f"{POD_CIDR},{SERVICE_CIDR},{node_cidr}"


@pytest.fixture(scope="module")
def vpn_config(cluster_cidrs: str) -> dict[str, str]:
    """VPN configuration for ProtonVPN with WireGuard."""
    return {
        "vpn-provider": "protonvpn",
        "cluster-cidrs": cluster_cidrs,
    }


@pytest.fixture(scope="module")
def wireguard_private_key() -> str:
    """WireGuard private key from environment."""
    return os.environ["WIREGUARD_PRIVATE_KEY"]


@pytest.fixture(scope="module")
def charm_path() -> Path:
    """Pack the gluetun charm once per test module."""
    return pack_gluetun_charm()


@pytest.fixture(scope="module")
def gluetun_deployed(
    juju: jubilant.Juju,
    charm_path: Path,
    vpn_config: dict[str, str],
    wireguard_private_key: str,
) -> None:
    """Ensure gluetun is deployed with VPN config."""
    status = juju.status()
    if "gluetun" in status.apps:
        return

    secret_uri = create_vpn_secret(juju, wireguard_private_key)
    deploy_gluetun_charm(juju, charm_path, vpn_config, secret_uri)
    grant_secret_to_app(juju, "vpn-key", "gluetun")
    wait_for_active_idle(juju)


@pytest.fixture(scope="module")
def multimeter_deployed(juju: jubilant.Juju) -> None:
    """Ensure charmarr-multimeter is deployed."""
    status = juju.status()
    if "charmarr-multimeter" not in status.apps:
        deploy_multimeter(juju)
        wait_for_active_idle(juju)


@pytest.fixture(scope="module")
def multimeter_related_to_gluetun(
    juju: jubilant.Juju, gluetun_deployed: None, multimeter_deployed: None
) -> None:
    """Ensure multimeter is related to gluetun via vpn-gateway."""
    status = juju.status()
    app = status.apps.get("charmarr-multimeter")
    if app and "vpn-gateway" in app.relations:
        return
    juju.integrate("charmarr-multimeter:vpn-gateway", "gluetun:vpn-gateway")
    wait_for_active_idle(juju)
