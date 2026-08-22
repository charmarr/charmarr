# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for radarr-k8s integration tests."""

import jubilant
from pytest_bdd import given, parsers, then

from charmarr_lib.testing import (
    ArrCredentials,
    get_ingress_url,
    http_from_unit,
    wait_for_active_idle,
)


@given("radarr is deployed", target_fixture="radarr_deployed")
def radarr_is_deployed(radarr_deployed: None) -> None:
    """Ensure radarr is deployed."""


@given(parsers.parse('radarr is configured with trash-profiles "{profiles}"'))
def configure_trash_profiles(juju: jubilant.Juju, profiles: str) -> None:
    """Configure radarr with trash-profiles."""
    juju.config("radarr", {"trash-profiles": profiles})
    wait_for_active_idle(juju)


@then("radarr should be accessible via ingress")
def radarr_accessible_via_ingress(juju: jubilant.Juju, credentials: ArrCredentials) -> None:
    """Verify radarr is accessible via ingress."""
    base_url = get_ingress_url(juju, "radarr")
    assert base_url is not None, "Ingress provider published no URL for radarr"

    response = http_from_unit(
        juju,
        "radarr/0",
        f"{base_url}/api/v3/system/status",
        headers={"X-Api-Key": credentials.api_key},
    )
    assert response.status_code == 200
