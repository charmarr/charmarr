# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""VXLAN configuration step definitions for gluetun-k8s integration tests."""

import jubilant
from pytest_bdd import given, parsers, then, when

from tests.integration.helpers import get_gateway_client_config

DEFAULT_VXLAN_ID = "42"


def _wait_for_config_settle(juju: jubilant.Juju) -> None:
    """Wait for model to settle after config changes.

    Config changes trigger pod restarts via StatefulSet config-hash annotations.
    Both gateway and client pods restart, causing transient container errors
    while the gateway is temporarily unreachable. Wait without error= to
    tolerate these transient states.
    """
    juju.wait(jubilant.all_active, delay=5, successes=3, timeout=60 * 20)
    juju.wait(jubilant.all_agents_idle, delay=5, timeout=60 * 5)


@given("the gluetun config is set to defaults")
def reset_gluetun_config(juju: jubilant.Juju, cluster_cidrs: str) -> None:
    """Ensure gluetun config is at known defaults before each scenario."""
    juju.cli("config", "gluetun", f"vxlan-id={DEFAULT_VXLAN_ID}")
    juju.cli("config", "gluetun", f"cluster-cidrs={cluster_cidrs}")
    _wait_for_config_settle(juju)


@when(parsers.parse('the gluetun config "{key}" is set to "{value}"'))
def set_gluetun_config(juju: jubilant.Juju, key: str, value: str) -> None:
    """Set a config option on the gluetun charm."""
    juju.cli("config", "gluetun", f"{key}={value}")
    _wait_for_config_settle(juju)


@when('the gluetun config "cluster-cidrs" is updated')
def update_cluster_cidrs(juju: jubilant.Juju, cluster_cidrs: str) -> None:
    """Update cluster-cidrs config with test value."""
    new_cidrs = f"{cluster_cidrs},192.168.100.0/24"
    juju.cli("config", "gluetun", f"cluster-cidrs={new_cidrs}")
    _wait_for_config_settle(juju)


@then(parsers.parse("the multimeter client containers should use VXLAN ID {vxlan_id:d}"))
def multimeter_uses_vxlan_id(juju: jubilant.Juju, vxlan_id: int) -> None:
    """Verify multimeter's gateway client config has correct VXLAN_ID."""
    config = get_gateway_client_config(juju)
    value = config.get("vxlan-id", "")
    assert value == str(vxlan_id), f"Expected vxlan-id={vxlan_id}, got {value}"


@then("the multimeter client containers should use the new cluster CIDRs")
def multimeter_uses_new_cidrs(juju: jubilant.Juju) -> None:
    """Verify multimeter's gateway client config has updated NOT_ROUTED_TO_GATEWAY_CIDRS."""
    config = get_gateway_client_config(juju)
    value = config.get("not-routed-to-gateway-cidrs", "")
    assert "192.168.100.0/24" in value, f"New CIDR not found in: {value}"
