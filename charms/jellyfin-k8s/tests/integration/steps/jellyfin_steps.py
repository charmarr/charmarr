# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for jellyfin-k8s integration tests."""

import json
import subprocess

import jubilant
from pytest_bdd import given, parsers, then, when

from _jellyfin import WEBUI_PORT
from charmarr_lib.testing import get_ingress_ip, http_from_unit


@given("jellyfin is deployed", target_fixture="jellyfin_deployed")
def jellyfin_is_deployed(jellyfin_deployed: None) -> None:
    """Ensure jellyfin is deployed."""


@then("jellyfin public info endpoint should respond")
def jellyfin_public_info_responds(juju: jubilant.Juju) -> None:
    """Verify jellyfin /System/Info/Public endpoint responds."""
    url = f"http://jellyfin:{WEBUI_PORT}/System/Info/Public"
    response = http_from_unit(juju, "jellyfin/0", url)
    assert response.status_code == 200
    assert "Version" in response.body


@then("jellyfin should report the startup wizard as completed")
def jellyfin_wizard_completed(juju: jubilant.Juju) -> None:
    """Verify the charm ran the startup wizard without operator involvement."""
    url = f"http://jellyfin:{WEBUI_PORT}/System/Info/Public"
    response = http_from_unit(juju, "jellyfin/0", url)
    assert response.status_code == 200
    assert json.loads(response.body)["StartupWizardCompleted"] is True


@then(parsers.parse("an {label} secret should exist for {app}"))
def secret_exists(juju: jubilant.Juju, label: str, app: str) -> None:
    """Assert the charm created a secret with the given label."""
    secrets = json.loads(juju.cli("list-secrets", "--format=json"))
    found = any(
        info.get("owner") == app and info.get("label") == label for info in secrets.values()
    )
    assert found, f"No '{label}' secret found for {app}"


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
