# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for seerr-k8s integration tests."""

import jubilant
from pytest_bdd import given, then

from _seerr import WEBUI_PORT
from charmarr_lib.testing import get_ingress_url, http_from_unit


@given("seerr is deployed", target_fixture="seerr_deployed")
def seerr_is_deployed(seerr_deployed: None) -> None:
    """Ensure seerr is deployed."""


@then("seerr should be waiting for setup")
def seerr_waiting_for_setup(juju: jubilant.Juju) -> None:
    """Verify seerr is in waiting status for setup."""
    status = juju.status()
    app = status.apps.get("seerr")
    assert app is not None, "seerr app not found"
    unit = app.units.get("seerr/0")
    assert unit is not None, "seerr/0 unit not found"

    assert unit.workload_status.current == "waiting"
    assert "setup" in unit.workload_status.message.lower()


@then("seerr status API should be accessible")
def seerr_status_api_accessible(juju: jubilant.Juju) -> None:
    """Verify seerr status API is accessible."""
    url = f"http://localhost:{WEBUI_PORT}/api/v1/status"
    response = http_from_unit(juju, "seerr/0", url)
    assert response.status_code == 200


@then("seerr should be accessible via ingress")
def seerr_accessible_via_ingress(juju: jubilant.Juju) -> None:
    """Verify seerr is accessible via ingress."""
    base_url = get_ingress_url(juju, "seerr")
    assert base_url is not None, "Ingress provider published no URL for seerr"

    response = http_from_unit(juju, "seerr/0", f"{base_url}/api/v1/status")
    assert response.status_code == 200
