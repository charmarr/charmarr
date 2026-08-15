# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for jellyfin-k8s integration tests."""

import subprocess

import jubilant
from pytest_bdd import given, then, when

from _jellyfin import WEBUI_PORT
from charmarr_lib.testing import get_ingress_ip, http_from_unit


@given("jellyfin is deployed", target_fixture="jellyfin_deployed")
def jellyfin_is_deployed(jellyfin_deployed: None) -> None:
    """Ensure jellyfin is deployed."""


@given("jellyfin startup wizard is completed")
def complete_startup_wizard(juju: jubilant.Juju) -> None:
    """Complete the Jellyfin startup wizard via API.

    Jellyfin starts with an incomplete startup wizard, leaving the charm in
    'waiting' status. Complete it via the API so the charm can reach 'active'.
    """
    status = juju.status()
    unit = status.apps["jellyfin"].units.get("jellyfin/0")
    if unit and unit.workload_status.current == "active":
        return

    juju.exec(
        "curl", "-s", "-X", "POST",
        f"http://localhost:{WEBUI_PORT}/Startup/Complete",
        unit="jellyfin/0",
    )


@then("jellyfin public info endpoint should respond")
def jellyfin_public_info_responds(juju: jubilant.Juju) -> None:
    """Verify jellyfin /System/Info/Public endpoint responds."""
    url = f"http://jellyfin:{WEBUI_PORT}/System/Info/Public"
    response = http_from_unit(juju, "jellyfin/0", url)
    assert response.status_code == 200
    assert "Version" in response.body


@then("jellyfin should show setup-incomplete status")
def jellyfin_setup_incomplete_status(juju: jubilant.Juju) -> None:
    """Verify jellyfin shows setup-incomplete status message."""
    status = juju.status()
    jellyfin_status = status.apps["jellyfin"]
    unit = jellyfin_status.units.get("jellyfin/0")
    assert unit is not None, "jellyfin/0 unit not found"
    assert unit.workload_status.current == "waiting"
    assert "setup" in unit.workload_status.message.lower()


@then("jellyfin should be accessible via ingress")
def jellyfin_accessible_via_ingress(juju: jubilant.Juju) -> None:
    """Verify jellyfin is accessible via ingress."""
    ingress_ip = get_ingress_ip(juju, "istio-ingress")
    assert ingress_ip is not None, "Could not get ingress IP"

    url = f"http://{ingress_ip}:80/System/Info/Public"
    response = http_from_unit(juju, "jellyfin/0", url)
    assert response.status_code == 200


@when("hardware-transcoding is enabled")
def enable_hw_transcoding(juju: jubilant.Juju) -> None:
    """Enable hardware transcoding config."""
    juju.config("jellyfin", {"hardware-transcoding": "true"})
    juju.wait(jubilant.all_agents_idle, delay=5, timeout=60 * 5)


@when("hardware-transcoding is disabled")
def disable_hw_transcoding(juju: jubilant.Juju) -> None:
    """Disable hardware transcoding config."""
    juju.config("jellyfin", {"hardware-transcoding": "false"})
    juju.wait(jubilant.all_agents_idle, delay=5, timeout=60 * 5)


@then("the jellyfin StatefulSet should have dev-dri volume mount")
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
            "jellyfin",
            "-o",
            "jsonpath={.spec.template.spec.volumes[*].name}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    volumes = result.stdout.split()
    assert "dev-dri" in volumes, f"dev-dri volume not found in: {volumes}"


@then("the jellyfin StatefulSet should not have dev-dri volume mount")
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
            "jellyfin",
            "-o",
            "jsonpath={.spec.template.spec.volumes[*].name}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    volumes = result.stdout.split()
    assert "dev-dri" not in volumes, f"dev-dri volume unexpectedly found in: {volumes}"
