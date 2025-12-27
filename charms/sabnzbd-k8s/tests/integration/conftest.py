# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for sabnzbd-k8s integration tests."""

import os
from pathlib import Path

import jubilant
import pytest

from charmarr_lib.testing import deploy_multimeter, vpn_creds_available, wait_for_active_idle
from charmarr_lib.testing.steps.storage import deploy_storage_from_charmhub
from tests.integration.helpers import (
    ApiKey,
    deploy_sabnzbd_charm,
    get_sabnzbd_api_key,
    pack_sabnzbd_charm,
)

pytest_plugins = [
    "charmarr_lib.testing.steps.multimeter",
    "charmarr_lib.testing.steps.storage",
    "charmarr_lib.testing.steps.gluetun",
    "charmarr_lib.testing.steps.mesh",
    "charmarr_lib.testing.steps.download_client",
    "tests.integration.steps.sabnzbd_steps",
]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark VPN tests as xfail if credentials not available."""
    if vpn_creds_available():
        return

    for item in items:
        if "vpn" in str(item.fspath):
            item.add_marker(
                pytest.mark.xfail(
                    reason="WIREGUARD_PRIVATE_KEY environment variable required",
                    run=False,
                )
            )


@pytest.fixture(scope="module")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_sabnzbd_charm()


@pytest.fixture(scope="module")
def sabnzbd_deployed(juju: jubilant.Juju, charm_path: Path, storage_deployed: None) -> None:
    """Ensure sabnzbd is deployed with storage relation."""
    status = juju.status()
    if "sabnzbd" in status.apps:
        return
    deploy_sabnzbd_charm(juju, charm_path)


@pytest.fixture(scope="module")
def storage_deployed(juju: jubilant.Juju) -> None:
    """Ensure charmarr-storage is deployed."""
    deploy_storage_from_charmhub(juju)


@pytest.fixture(scope="module")
def api_key(juju: jubilant.Juju, sabnzbd_deployed: None) -> ApiKey:
    """Get sabnzbd API key after deployment."""
    key = get_sabnzbd_api_key(juju)
    assert key is not None, "Failed to retrieve sabnzbd API key"
    return key


@pytest.fixture(scope="module")
def multimeter_related(juju: jubilant.Juju, sabnzbd_deployed: None) -> None:
    """Ensure multimeter is related to sabnzbd via download-client."""
    status = juju.status()
    if "charmarr-multimeter" not in status.apps:
        deploy_multimeter(juju)
        wait_for_active_idle(juju)

    app = status.apps.get("charmarr-multimeter")
    if not app or "download-client" not in app.relations:
        juju.integrate("charmarr-multimeter:download-client", "sabnzbd:download-client")
        wait_for_active_idle(juju)
