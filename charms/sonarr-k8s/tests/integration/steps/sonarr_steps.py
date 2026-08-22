# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for sonarr-k8s integration tests."""

import jubilant
from pytest_bdd import given, parsers, then

from charmarr_lib.testing import (
    ArrCredentials,
    get_ingress_url,
    http_from_unit,
    wait_for_active_idle,
)


@given("sonarr is deployed", target_fixture="sonarr_deployed")
def sonarr_is_deployed(sonarr_deployed: None) -> None:
    """Ensure sonarr is deployed."""


@given(parsers.parse('sonarr is configured with trash-profiles "{profiles}"'))
def configure_trash_profiles(juju: jubilant.Juju, profiles: str) -> None:
    """Configure sonarr with trash-profiles."""
    juju.config("sonarr", {"trash-profiles": profiles})
    wait_for_active_idle(juju)


@then("sonarr should be accessible via ingress")
def sonarr_accessible_via_ingress(juju: jubilant.Juju, credentials: ArrCredentials) -> None:
    """Verify sonarr is accessible via ingress."""
    base_url = get_ingress_url(juju, "sonarr")
    assert base_url is not None, "Ingress provider published no URL for sonarr"

    response = http_from_unit(
        juju,
        "sonarr/0",
        f"{base_url}/api/v3/system/status",
        headers={"X-Api-Key": credentials.api_key},
    )
    assert response.status_code == 200
