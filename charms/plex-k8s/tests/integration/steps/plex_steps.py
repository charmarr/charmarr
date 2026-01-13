# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for plex-k8s integration tests."""

import subprocess

import jubilant
from pytest_bdd import given, then, when

from _plex import WEBUI_PORT
from charmarr_lib.testing import get_ingress_ip, http_from_unit


@given("plex is deployed", target_fixture="plex_deployed")
def plex_is_deployed(plex_deployed: None) -> None:
    """Ensure plex is deployed."""


@then("plex identity endpoint should respond")
def plex_identity_responds(juju: jubilant.Juju) -> None:
    """Verify plex /identity endpoint responds."""
    url = f"http://plex:{WEBUI_PORT}/identity"
    response = http_from_unit(juju, "plex/0", url)
    assert response.status_code == 200
    assert "MediaContainer" in response.body


@then("plex should show unclaimed status")
def plex_unclaimed_status(juju: jubilant.Juju) -> None:
    """Verify plex shows unclaimed status message."""
    status = juju.status()
    plex_status = status.apps["plex"]
    unit = plex_status.units.get("plex/0")
    assert unit is not None, "plex/0 unit not found"
    assert unit.workload_status.current == "blocked"
    assert "claim-token" in unit.workload_status.message.lower()


@then("plex should be accessible via ingress")
def plex_accessible_via_ingress(juju: jubilant.Juju) -> None:
    """Verify plex is accessible via ingress."""
    ingress_ip = get_ingress_ip(juju, "istio-ingress")
    assert ingress_ip is not None, "Could not get ingress IP"

    url = f"http://{ingress_ip}:443/identity"
    response = http_from_unit(juju, "plex/0", url)
    assert response.status_code == 200


@when("hardware-transcoding is enabled")
def enable_hw_transcoding(juju: jubilant.Juju) -> None:
    """Enable hardware transcoding config."""
    juju.config("plex", {"hardware-transcoding": "true"})
    juju.wait(jubilant.all_agents_idle, delay=5, timeout=60 * 5)


@when("hardware-transcoding is disabled")
def disable_hw_transcoding(juju: jubilant.Juju) -> None:
    """Disable hardware transcoding config."""
    juju.config("plex", {"hardware-transcoding": "false"})
    juju.wait(jubilant.all_agents_idle, delay=5, timeout=60 * 5)


@then("the plex StatefulSet should have dev-dri volume mount")
def verify_dri_mount(juju: jubilant.Juju) -> None:
    """Verify StatefulSet has /dev/dri volume mount."""
    model = juju.status().model.name
    result = subprocess.run(
        [
            "kubectl",
            "-n",
            model,
            "get",
            "statefulset",
            "plex",
            "-o",
            "jsonpath={.spec.template.spec.volumes[*].name}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    volumes = result.stdout.split()
    assert "dev-dri" in volumes, f"dev-dri volume not found in: {volumes}"


@then("the plex StatefulSet should not have dev-dri volume mount")
def verify_no_dri_mount(juju: jubilant.Juju) -> None:
    """Verify StatefulSet does not have /dev/dri volume mount."""
    model = juju.status().model.name
    result = subprocess.run(
        [
            "kubectl",
            "-n",
            model,
            "get",
            "statefulset",
            "plex",
            "-o",
            "jsonpath={.spec.template.spec.volumes[*].name}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    volumes = result.stdout.split()
    assert "dev-dri" not in volumes, f"dev-dri volume unexpectedly found in: {volumes}"
