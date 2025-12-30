# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for prowlarr-k8s integration tests."""

import json
import os
from pathlib import Path

import jubilant
import pytest
from pytest_jubilant import pack

from charmarr_lib.testing import ArrCredentials, vpn_creds_available, wait_for_active_idle
from charmarr_lib.testing.steps.storage import deploy_storage_from_charmhub
from tests.integration.helpers import (
    CHARMS_DIR,
    deploy_prowlarr_charm,
    deploy_radarr_charm,
    get_prowlarr_credentials,
    pack_prowlarr_charm,
)

FLARESOLVERR_CHANNEL = os.environ.get("CHARMARR_FLARESOLVERR_CHANNEL", "latest/edge")

pytest_plugins = [
    "charmarr_lib.testing.steps.storage",
    "charmarr_lib.testing.steps.gluetun",
    "charmarr_lib.testing.steps.mesh",
    "charmarr_lib.testing.steps.arr",
    "tests.integration.steps.prowlarr_steps",
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


@pytest.fixture(scope="session")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_prowlarr_charm()


@pytest.fixture(scope="session")
def radarr_charm_path() -> Path:
    """Pack radarr charm for integration testing."""
    if env_paths := os.environ.get("ARR_CHARM_PATHS"):
        paths = json.loads(env_paths)
        if "radarr-k8s" in paths:
            return Path(paths["radarr-k8s"])
    return pack(CHARMS_DIR / "radarr-k8s")


@pytest.fixture(scope="module")
def prowlarr_deployed(juju: jubilant.Juju, charm_path: Path) -> None:
    """Ensure prowlarr is deployed."""
    status = juju.status()
    if "prowlarr" in status.apps:
        return
    deploy_prowlarr_charm(juju, charm_path)


@pytest.fixture(scope="module")
def storage_deployed(juju: jubilant.Juju) -> None:
    """Ensure charmarr-storage is deployed."""
    deploy_storage_from_charmhub(juju)


@pytest.fixture(scope="module")
def credentials(juju: jubilant.Juju, prowlarr_deployed: None) -> ArrCredentials:
    """Get prowlarr credentials after deployment."""
    creds = get_prowlarr_credentials(juju)
    assert creds is not None, "Failed to retrieve prowlarr credentials"
    return creds


@pytest.fixture(scope="module")
def flaresolverr_deployed(juju: jubilant.Juju) -> None:
    """Ensure flaresolverr is deployed from Charmhub."""
    status = juju.status()
    if "flaresolverr" in status.apps:
        return
    juju.deploy("flaresolverr-k8s", app="flaresolverr", channel=FLARESOLVERR_CHANNEL, trust=True)
    wait_for_active_idle(juju)


@pytest.fixture(scope="module")
def flaresolverr_related(
    juju: jubilant.Juju, prowlarr_deployed: None, flaresolverr_deployed: None
) -> None:
    """Ensure prowlarr is related to flaresolverr."""
    status = juju.status()
    app = status.apps.get("prowlarr")
    if app and "flaresolverr" in app.relations:
        return
    juju.integrate("prowlarr:flaresolverr", "flaresolverr:flaresolverr")
    wait_for_active_idle(juju)


@pytest.fixture(scope="module")
def radarr_deployed(juju: jubilant.Juju, radarr_charm_path: Path, storage_deployed: None) -> None:
    """Ensure radarr is deployed with storage."""
    status = juju.status()
    if "radarr" in status.apps:
        return
    deploy_radarr_charm(juju, radarr_charm_path)


@pytest.fixture(scope="module")
def radarr_related(juju: jubilant.Juju, prowlarr_deployed: None, radarr_deployed: None) -> None:
    """Ensure radarr is related to prowlarr via media-indexer."""
    status = juju.status()
    app = status.apps.get("radarr")
    if app and "media-indexer" in app.relations:
        return
    juju.integrate("radarr:media-indexer", "prowlarr:media-indexer")
    wait_for_active_idle(juju)
