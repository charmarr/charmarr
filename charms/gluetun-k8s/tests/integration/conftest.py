# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for gluetun-k8s integration tests."""

import os
from collections.abc import Generator
from pathlib import Path

import jubilant
import pytest

from charmarr_lib.testing import (
    create_vpn_secret,
    get_node_cidr,
    grant_secret_to_app,
    vpn_creds_available,
    wait_for_active_idle,
)
from tests.integration.cluster import discover_cluster_cidrs
from tests.integration.diagnostics import (
    log_cluster_topology,
    log_failure_context,
    warn_on_cidr_overlap,
)
from tests.integration.helpers import deploy_gluetun_charm, pack_gluetun_charm

pytest_plugins = [
    "charmarr_lib.testing.steps.multimeter",
    "charmarr_lib.testing.steps.mesh",
    "charmarr_lib.testing.steps.gluetun",
    "tests.integration.steps.common_steps",
    "tests.integration.steps.vpn_steps",
    "tests.integration.steps.vxlan_steps",
    "tests.integration.steps.cleanup_steps",
]

POD_CIDR = "10.1.0.0/16"
SERVICE_CIDR = "10.152.183.0/24"


@pytest.fixture(scope="session", autouse=True)
def cluster_topology() -> None:
    """Record cluster addressing once per session, whether or not tests fail."""
    log_cluster_topology()
    warn_on_cidr_overlap(POD_CIDR, SERVICE_CIDR)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator:
    report = yield
    if report.failed and report.when in ("setup", "call"):
        log_failure_context()
    return report


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark all integration tests as xfail if VPN credentials not available."""
    if vpn_creds_available():
        return

    xfail_marker = pytest.mark.xfail(
        reason="WIREGUARD_PRIVATE_KEY environment variable required",
        run=False,
    )
    for item in items:
        item.add_marker(xfail_marker)


@pytest.fixture(scope="module")
def cluster_cidrs() -> str:
    """Build cluster CIDRs covering pod, service, node and any other pod network in use."""
    declared = [POD_CIDR, SERVICE_CIDR, get_node_cidr()]
    return ",".join(discover_cluster_cidrs(declared))


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
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
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
