# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Common step definitions for gluetun-k8s integration tests."""

import jubilant
from pytest_bdd import given, then

from tests.integration.helpers import (
    extract_vpn_ip_from_status,
    get_external_ip,
    get_gluetun_status,
    get_vxlan_info,
)


@given("the gluetun-k8s charm is deployed with valid VPN config")
def deploy_gluetun(gluetun_deployed: None) -> None:
    """Deploy gluetun with VPN configuration (uses fixture)."""


@given("charmarr-multimeter is related to gluetun via vpn-gateway")
def relate_multimeter_gluetun(juju: jubilant.Juju) -> None:
    """Integrate multimeter with gluetun via vpn-gateway."""
    from charmarr_lib.testing import wait_for_active_idle

    status = juju.status()
    app = status.apps.get("charmarr-multimeter")
    if app and "vpn-gateway" in app.relations:
        return
    juju.integrate("charmarr-multimeter:vpn-gateway", "gluetun:vpn-gateway")
    wait_for_active_idle(juju)


@then("the gluetun charm should be active")
def gluetun_active(juju: jubilant.Juju) -> None:
    """Verify gluetun charm is active."""
    current, message = get_gluetun_status(juju)
    assert current == "active", f"Gluetun status: {current} - {message}"


@then("the gluetun charm status should show a VPN IP")
def gluetun_has_vpn_ip(juju: jubilant.Juju) -> None:
    """Verify gluetun status message contains VPN IP."""
    _, message = get_gluetun_status(juju)
    ip = extract_vpn_ip_from_status(message)
    assert ip is not None, f"No VPN IP in status message: {message}"


@then("the multimeter external IP should match the gluetun VPN IP")
def multimeter_ip_matches_gluetun(juju: jubilant.Juju) -> None:
    """Verify multimeter routes through VPN (same external IP as gluetun)."""
    _, message = get_gluetun_status(juju)
    gluetun_ip = extract_vpn_ip_from_status(message)
    assert gluetun_ip is not None, f"No VPN IP in gluetun status: {message}"

    multimeter_ip = get_external_ip(juju)
    assert multimeter_ip is not None, "Could not get multimeter external IP"
    assert multimeter_ip == gluetun_ip, (
        f"Multimeter IP {multimeter_ip} != gluetun VPN IP {gluetun_ip}"
    )


@then("the multimeter should have a vxlan interface")
def multimeter_has_vxlan(juju: jubilant.Juju) -> None:
    """Verify multimeter has VXLAN interface configured."""
    info = get_vxlan_info(juju)
    assert info.exists, "VXLAN interface not found on multimeter"
    assert info.ip, "VXLAN interface has no IP assigned"
