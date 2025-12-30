# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""FlareSolverr-specific step definitions."""

import jubilant
from pytest_bdd import given, then

from charmarr_lib.testing import http_request


@given("flaresolverr is deployed")
def deploy_flaresolverr(flaresolverr_deployed: None) -> None:
    """Deploy flaresolverr (uses fixture)."""


@then("the flaresolverr charm should be active")
def flaresolverr_active(juju: jubilant.Juju) -> None:
    """Assert flaresolverr charm is active."""
    status = juju.status()
    app = status.apps["flaresolverr"]
    assert app.app_status.current == "active", (
        f"FlareSolverr status: {app.app_status.current} - {app.app_status.message}"
    )


@then("the flaresolverr health endpoint should respond")
def health_endpoint_responds(juju: jubilant.Juju) -> None:
    """Assert FlareSolverr health endpoint responds."""
    response = http_request(juju, "http://flaresolverr:8191/health")
    assert response.status_code == 200, (
        f"Health check failed: {response.status_code} - {response.body}"
    )
