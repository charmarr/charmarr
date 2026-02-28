# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd-specific step definitions."""

import jubilant
from pytest_bdd import given, then, when

from charmarr_lib.testing import get_ingress_ip, http_request
from tests.integration.helpers import ApiKey


@given("sabnzbd is deployed with storage relation")
def deploy_sabnzbd(sabnzbd_deployed: None) -> None:
    """Deploy sabnzbd with storage (uses fixture)."""


@when("the API key is retrieved from the sabnzbd secret")
def retrieve_api_key(api_key: ApiKey) -> None:
    """Retrieve API key (uses fixture, just validates it exists)."""
    assert api_key.api_key, "API key should not be empty"


@then("the sabnzbd charm should be active")
def sabnzbd_active(juju: jubilant.Juju) -> None:
    """Assert sabnzbd charm is active."""
    status = juju.status()
    app = status.apps["sabnzbd"]
    assert app.app_status.current == "active", (
        f"SABnzbd status: {app.app_status.current} - {app.app_status.message}"
    )


@then("an API key secret should exist for sabnzbd")
def api_key_secret_exists(api_key: ApiKey) -> None:
    """Assert API key secret exists."""
    assert api_key.secret_id, "API key secret should have an ID"


@then("the sabnzbd API should respond successfully")
def api_responds(juju: jubilant.Juju, api_key: ApiKey) -> None:
    """Assert SABnzbd API responds with version."""
    url = f"http://sabnzbd:8080/api?mode=version&output=json&apikey={api_key.api_key}"
    response = http_request(juju, url)
    assert response.status_code == 200, f"API failed: {response.status_code} - {response.body}"
    assert "version" in response.body, f"Expected version in response: {response.body}"


@then("the sabnzbd API should be accessible via ingress")
def api_accessible_via_ingress(juju: jubilant.Juju, api_key: ApiKey) -> None:
    """Assert API is accessible via istio-ingress."""
    ingress_ip = get_ingress_ip(juju)
    assert ingress_ip, "Could not get istio-ingress IP"

    url = f"http://{ingress_ip}:80/sabnzbd/api?mode=version&output=json&apikey={api_key.api_key}"
    response = http_request(juju, url)
    assert response.status_code == 200, (
        f"API via ingress failed: {response.status_code} - {response.body}"
    )
    assert "version" in response.body, f"Expected version in response: {response.body}"
