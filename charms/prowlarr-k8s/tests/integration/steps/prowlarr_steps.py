# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Prowlarr-specific step definitions."""

from urllib.parse import urlparse

import jubilant
from pytest_bdd import given, then

from charmarr_lib.testing import ArrCredentials, get_ingress_ip, http_from_unit


def _local_url(credentials: ArrCredentials, path: str) -> str:
    """Convert base_url to localhost URL for exec from unit."""
    parsed = urlparse(credentials.base_url)
    port = parsed.port or 80
    url_base = parsed.path.rstrip("/")
    return f"http://localhost:{port}{url_base}{path}"


@given("prowlarr is deployed")
def deploy_prowlarr(prowlarr_deployed: None) -> None:
    """Deploy prowlarr (uses fixture)."""


@given("flaresolverr is deployed from charmhub")
def deploy_flaresolverr(flaresolverr_deployed: None) -> None:
    """Deploy flaresolverr from Charmhub (uses fixture)."""


@given("prowlarr is related to flaresolverr")
def relate_prowlarr_flaresolverr(flaresolverr_related: None) -> None:
    """Relate prowlarr to flaresolverr (uses fixture)."""


@given("radarr is deployed with storage")
def deploy_radarr(radarr_deployed: None) -> None:
    """Deploy radarr with storage (uses fixture)."""


@then("prowlarr should have a flaresolverr proxy configured")
def flaresolverr_proxy_configured(juju: jubilant.Juju, credentials: ArrCredentials) -> None:
    """Assert prowlarr has a flaresolverr proxy configured via API."""
    url = _local_url(credentials, "/api/v1/indexerProxy")
    response = http_from_unit(juju, "prowlarr/0", url, headers={"X-Api-Key": credentials.api_key})
    assert response.status_code == 200, f"API call failed: {response.status_code}"

    proxies = response.json_body()
    flaresolverr_proxies = [p for p in proxies if p.get("implementation") == "FlareSolverr"]
    assert len(flaresolverr_proxies) > 0, f"No FlareSolverr proxy found: {proxies}"


@then("prowlarr should have radarr registered as an application")
def radarr_registered(juju: jubilant.Juju, credentials: ArrCredentials) -> None:
    """Assert prowlarr has radarr registered as an application."""
    url = _local_url(credentials, "/api/v1/applications")
    response = http_from_unit(juju, "prowlarr/0", url, headers={"X-Api-Key": credentials.api_key})
    assert response.status_code == 200, f"API call failed: {response.status_code}"

    apps = response.json_body()
    radarr_apps = [a for a in apps if "radarr" in a.get("name", "").lower()]
    assert len(radarr_apps) > 0, f"No radarr application found: {apps}"


@then("prowlarr should be accessible via ingress")
def prowlarr_accessible_via_ingress(juju: jubilant.Juju, credentials: ArrCredentials) -> None:
    """Verify prowlarr is accessible via ingress."""
    ingress_ip = get_ingress_ip(juju, "istio-ingress")
    assert ingress_ip is not None, "Could not get ingress IP"

    parsed = urlparse(credentials.base_url)
    url_base = parsed.path.rstrip("/")
    url = f"http://{ingress_ip}:443{url_base}/api/v1/system/status"
    response = http_from_unit(
        juju,
        "prowlarr/0",
        url,
        headers={"X-Api-Key": credentials.api_key},
    )
    assert response.status_code == 200
