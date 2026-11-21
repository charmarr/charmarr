# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for overseerr-k8s integration tests."""

import jubilant
from pytest_bdd import given, then

from _overseerr import WEBUI_PORT
from charmarr_lib.testing import http_from_unit


@given("overseerr is deployed", target_fixture="overseerr_deployed")
def overseerr_is_deployed(overseerr_deployed: None) -> None:
    """Ensure overseerr is deployed."""


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
