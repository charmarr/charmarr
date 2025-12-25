# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Cleanup and kill switch step definitions for gluetun-k8s integration tests."""

import jubilant
from pytest_bdd import then, when

from charmarr_lib.testing import wait_for_active_idle
from tests.integration.helpers import (
    check_connectivity,
    configmap_exists,
    get_container_info,
    get_network_policy_info,
)

GATEWAY_INIT = "vpn-route-init"
GATEWAY_SIDECAR = "vpn-route-sidecar"


@when("the vpn-gateway relation is removed")
def remove_vpn_gateway_relation(juju: jubilant.Juju) -> None:
    """Remove the vpn-gateway relation."""
    status = juju.status()
    app = status.apps.get("charmarr-multimeter")
    if app and "vpn-gateway" in app.relations:
        juju.cli("remove-relation", "charmarr-multimeter:vpn-gateway", "gluetun:vpn-gateway")
        wait_for_active_idle(juju)


@then("a NetworkPolicy for multimeter should exist")
def networkpolicy_exists(juju: jubilant.Juju) -> None:
    """Verify NetworkPolicy exists for multimeter."""
    namespace = juju.model
    info = get_network_policy_info(juju, namespace, "charmarr-multimeter-vpn-killswitch")
    assert info.exists, "Kill switch NetworkPolicy not found"


@then("the NetworkPolicy should allow traffic only to gateway and cluster CIDRs")
def networkpolicy_allows_cluster_cidrs(juju: jubilant.Juju, cluster_cidrs: str) -> None:
    """Verify NetworkPolicy egress rules contain expected CIDRs."""
    namespace = juju.model
    info = get_network_policy_info(juju, namespace, "charmarr-multimeter-vpn-killswitch")
    assert info.exists, "Kill switch NetworkPolicy not found"

    expected_cidrs = [c.strip() for c in cluster_cidrs.split(",")]
    for cidr in expected_cidrs:
        assert cidr in info.egress_cidrs, (
            f"Expected CIDR {cidr} not in NetworkPolicy: {info.egress_cidrs}"
        )


@then("the multimeter should not be able to reach external IPs")
def multimeter_cannot_reach_external(juju: jubilant.Juju) -> None:
    """Verify multimeter cannot reach external IPs (kill switch active)."""
    reachable = check_connectivity(juju, "ifconfig.me", timeout=10)
    assert not reachable, "Multimeter can still reach external IPs - kill switch not working"


@then("no NetworkPolicy for multimeter should exist")
def no_networkpolicy(juju: jubilant.Juju) -> None:
    """Verify NetworkPolicy does not exist for multimeter."""
    namespace = juju.model
    info = get_network_policy_info(juju, namespace, "charmarr-multimeter-vpn-killswitch")
    assert not info.exists, "Kill switch NetworkPolicy still exists after relation removal"


@then("the multimeter should not have gateway-init container")
def no_gateway_init(juju: jubilant.Juju) -> None:
    """Verify multimeter StatefulSet has no gateway-init container."""
    namespace = juju.model
    info = get_container_info(juju, namespace, "charmarr-multimeter")
    assert GATEWAY_INIT not in info.init_containers, (
        f"gateway-init still present: {info.init_containers}"
    )


@then("the multimeter should not have gateway-sidecar container")
def no_gateway_sidecar(juju: jubilant.Juju) -> None:
    """Verify multimeter StatefulSet has no gateway-sidecar container."""
    namespace = juju.model
    info = get_container_info(juju, namespace, "charmarr-multimeter")
    assert GATEWAY_SIDECAR not in info.containers, (
        f"gateway-sidecar still present: {info.containers}"
    )


@then("no gateway-client ConfigMap for multimeter should exist")
def no_gateway_configmap(juju: jubilant.Juju) -> None:
    """Verify gateway-client ConfigMap does not exist for multimeter."""
    namespace = juju.model
    exists = configmap_exists(juju, namespace, "charmarr-multimeter-gateway-client-config")
    assert not exists, "Gateway client ConfigMap still exists after relation removal"
