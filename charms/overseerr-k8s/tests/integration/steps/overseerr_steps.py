# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for overseerr-k8s integration tests."""

import os

import jubilant
from pytest_bdd import given, parsers, then

from _overseerr import WEBUI_PORT
from charmarr_lib.testing import get_ingress_ip, http_from_unit

# FIXME: Shared istio steps from charmarr_lib.testing.steps.mesh use wait_for_active_idle
# which waits for ALL apps to be active. Overseerr stays in "waiting" status because
# it requires Plex OAuth to initialize. Custom steps below only wait for istio apps.

ISTIO_CHANNEL = os.environ.get("CHARMARR_ISTIO_CHANNEL", "2/edge")


def _app_active(app_name: str):
    """Return a matcher that checks if a specific app is active."""

    def matcher(status: jubilant.Status) -> bool:
        app = status.apps.get(app_name)
        if not app:
            return False
        return app.app_status.current == "active"

    return matcher


@given("overseerr is deployed", target_fixture="overseerr_deployed")
def overseerr_is_deployed(overseerr_deployed: None) -> None:
    """Ensure overseerr is deployed."""


@given("istio-k8s is deployed")
def deploy_istio(juju: jubilant.Juju) -> None:
    """Deploy istio-k8s from Charmhub."""
    status = juju.status()
    if "istio-k8s" in status.apps:
        return
    juju.deploy("istio-k8s", app="istio-k8s", channel=ISTIO_CHANNEL, trust=True)
    juju.wait(_app_active("istio-k8s"), delay=5, timeout=60 * 10)


@given("istio-ingress is deployed")
def deploy_istio_ingress(juju: jubilant.Juju) -> None:
    """Deploy istio-ingress-k8s from Charmhub."""
    status = juju.status()
    if "istio-ingress" in status.apps:
        return
    juju.deploy("istio-ingress-k8s", app="istio-ingress", channel=ISTIO_CHANNEL, trust=True)
    juju.wait(_app_active("istio-ingress"), delay=5, timeout=60 * 10)


@given(parsers.parse("{app} is related to istio-ingress via istio-ingress-route"))
def relate_app_to_ingress(juju: jubilant.Juju, app: str) -> None:
    """Integrate an app with istio-ingress via istio-ingress-route relation."""
    status = juju.status()
    app_status = status.apps.get(app)
    if app_status and "istio-ingress-route" in app_status.relations:
        return
    juju.integrate(f"{app}:istio-ingress-route", "istio-ingress:istio-ingress-route")
    juju.wait(_app_active("istio-ingress"), delay=5, timeout=60 * 5)


@then("overseerr should be waiting for setup")
def overseerr_waiting_for_setup(juju: jubilant.Juju) -> None:
    """Verify overseerr is in waiting status for setup."""
    status = juju.status()
    app = status.apps.get("overseerr")
    assert app is not None, "overseerr app not found"
    unit = app.units.get("overseerr/0")
    assert unit is not None, "overseerr/0 unit not found"

    assert unit.workload_status.current == "waiting"
    assert "setup" in unit.workload_status.message.lower()


@then("overseerr status API should be accessible")
def overseerr_status_api_accessible(juju: jubilant.Juju) -> None:
    """Verify overseerr status API is accessible."""
    url = f"http://localhost:{WEBUI_PORT}/api/v1/status"
    response = http_from_unit(juju, "overseerr/0", url)
    assert response.status_code == 200


@then("overseerr should be accessible via ingress")
def overseerr_accessible_via_ingress(juju: jubilant.Juju) -> None:
    """Verify overseerr is accessible via ingress."""
    ingress_ip = get_ingress_ip(juju, "istio-ingress")
    assert ingress_ip is not None, "Could not get ingress IP"

    url = f"http://{ingress_ip}:443/api/v1/status"
    response = http_from_unit(juju, "overseerr/0", url)
    assert response.status_code == 200
