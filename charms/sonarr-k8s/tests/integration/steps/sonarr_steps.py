# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for sonarr-k8s integration tests."""

from urllib.parse import urlparse

import jubilant
from pytest_bdd import given, parsers, then

from charmarr_lib.testing import (
    ArrCredentials,
    get_ingress_ip,
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
    ingress_ip = get_ingress_ip(juju, "istio-ingress")
    assert ingress_ip is not None, "Could not get ingress IP"

    parsed = urlparse(credentials.base_url)
    url_base = parsed.path.rstrip("/")
    url = f"http://{ingress_ip}:80{url_base}/api/v3/system/status"
    response = http_from_unit(
        juju,
        "sonarr/0",
        url,
        headers={"X-Api-Key": credentials.api_key},
    )
    assert response.status_code == 200
