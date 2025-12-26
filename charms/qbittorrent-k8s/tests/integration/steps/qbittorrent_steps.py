# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""qBittorrent-specific step definitions."""

import jubilant
from pytest_bdd import given, parsers, then, when

from charmarr_lib.testing import (
    get_app_relation_data,
    get_ingress_ip,
    http_request,
    wait_for_active_idle,
)
from tests.integration.helpers import Credentials


@given("qbittorrent is deployed with storage relation")
def deploy_qbittorrent(qbittorrent_deployed: None) -> None:
    """Deploy qbittorrent with storage (uses fixture)."""


@given("qbittorrent is related to gluetun via vpn-gateway")
def relate_qbittorrent_gluetun(juju: jubilant.Juju, qbittorrent_deployed: None) -> None:
    """Integrate qbittorrent with gluetun via vpn-gateway."""
    status = juju.status()
    app = status.apps.get("qbittorrent")
    if app and "vpn-gateway" in app.relations:
        return
    juju.integrate("qbittorrent:vpn-gateway", "gluetun:vpn-gateway")
    wait_for_active_idle(juju)


@given("qbittorrent is related to istio-ingress via istio-ingress-route")
def relate_qbittorrent_ingress(juju: jubilant.Juju, qbittorrent_deployed: None) -> None:
    """Integrate qbittorrent with istio-ingress via istio-ingress-route."""
    status = juju.status()
    app = status.apps.get("qbittorrent")
    if app and "istio-ingress-route" in app.relations:
        return
    juju.integrate("qbittorrent:istio-ingress-route", "istio-ingress:istio-ingress-route")
    wait_for_active_idle(juju)


@when("credentials are retrieved from the qbittorrent secret")
def retrieve_credentials(credentials: Credentials) -> None:
    """Retrieve credentials (uses fixture, just validates they exist)."""
    assert credentials.username, "Username should not be empty"
    assert credentials.password, "Password should not be empty"


@then("the qbittorrent charm should be active")
def qbittorrent_active(juju: jubilant.Juju) -> None:
    """Assert qbittorrent charm is active."""
    status = juju.status()
    app = status.apps["qbittorrent"]
    assert app.app_status.current == "active", (
        f"qBittorrent status: {app.app_status.current} - {app.app_status.message}"
    )


@then("a credentials secret should exist for qbittorrent")
def credentials_secret_exists(credentials: Credentials) -> None:
    """Assert credentials secret exists."""
    assert credentials.secret_id, "Credentials secret should have an ID"


@then("the qbittorrent WebUI should authenticate successfully")
def webui_authenticates(juju: jubilant.Juju, credentials: Credentials) -> None:
    """Assert WebUI login succeeds and API is accessible."""
    login_url = "http://qbittorrent:8080/api/v2/auth/login"
    login_body = f"username={credentials.username}&password={credentials.password}"
    login_response = http_request(
        juju,
        login_url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=login_body,
    )
    assert login_response.status_code == 200, (
        f"Login failed: {login_response.status_code} - {login_response.body}"
    )
    assert login_response.body == "Ok.", f"Login response: {login_response.body}"

    sid = login_response.cookies.get("SID")
    assert sid, f"No SID cookie in response: {login_response.cookies}"

    version_url = "http://qbittorrent:8080/api/v2/app/version"
    version_response = http_request(juju, version_url, headers={"Cookie": f"SID={sid}"})
    assert version_response.status_code == 200, (
        f"Expected 200, got {version_response.status_code}: {version_response.body}"
    )


@then("the download-client relation should contain api_url")
def relation_has_api_url(juju: jubilant.Juju) -> None:
    """Assert download-client relation contains api_url."""
    data = get_app_relation_data(juju, "charmarr-multimeter/0", "download-client")
    assert data is not None, "No relation data found"
    assert "api_url" in data, f"api_url not in relation data: {data}"


@then("the download-client relation should contain credentials_secret_id")
def relation_has_credentials(juju: jubilant.Juju) -> None:
    """Assert download-client relation contains credentials_secret_id."""
    data = get_app_relation_data(juju, "charmarr-multimeter/0", "download-client")
    assert data is not None, "No relation data found"
    assert "credentials_secret_id" in data, f"credentials_secret_id not in relation data: {data}"


@then(parsers.parse('the download-client relation should contain client type "{expected}"'))
def relation_has_client_type(juju: jubilant.Juju, expected: str) -> None:
    """Assert download-client relation contains expected client type."""
    data = get_app_relation_data(juju, "charmarr-multimeter/0", "download-client")
    assert data is not None, "No relation data found"
    assert data.get("client") == expected, f"Expected client={expected}, got: {data.get('client')}"


@then("the qbittorrent WebUI should be accessible via ingress")
def webui_accessible_via_ingress(juju: jubilant.Juju, credentials: Credentials) -> None:
    """Assert WebUI is accessible via istio-ingress."""
    ingress_ip = get_ingress_ip(juju)
    assert ingress_ip, "Could not get istio-ingress IP"

    base_url = f"http://{ingress_ip}:443/qbt"
    login_url = f"{base_url}/api/v2/auth/login"
    login_body = f"username={credentials.username}&password={credentials.password}"
    login_response = http_request(
        juju,
        login_url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=login_body,
    )
    assert login_response.status_code == 200, (
        f"Login via ingress failed: {login_response.status_code} - {login_response.body}"
    )

    sid = login_response.cookies.get("SID")
    assert sid, f"No SID cookie in ingress response: {login_response.cookies}"

    version_url = f"{base_url}/api/v2/app/version"
    version_response = http_request(juju, version_url, headers={"Cookie": f"SID={sid}"})
    assert version_response.status_code == 200, (
        f"Expected 200, got {version_response.status_code}: {version_response.body}"
    )
