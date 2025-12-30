# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for radarr-k8s integration tests."""

import os
from pathlib import Path

import jubilant
import pytest

from charmarr_lib.testing import ArrCredentials
from charmarr_lib.testing.steps.storage import deploy_storage_from_charmhub
from tests.integration.helpers import (
    deploy_prowlarr_charm,
    deploy_radarr_charm,
    get_radarr_credentials,
    pack_prowlarr_charm,
    pack_radarr_charm,
)

pytest_plugins = [
    "charmarr_lib.testing.steps.storage",
    "charmarr_lib.testing.steps.arr",
    "charmarr_lib.testing.steps.mesh",
    "tests.integration.steps.radarr_steps",
]


@pytest.fixture(scope="session")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_radarr_charm()


@pytest.fixture(scope="module")
def storage_deployed(juju: jubilant.Juju) -> None:
    """Ensure charmarr-storage is deployed."""
    deploy_storage_from_charmhub(juju)


@pytest.fixture(scope="module")
def radarr_deployed(juju: jubilant.Juju, charm_path: Path, storage_deployed: None) -> None:
    """Ensure radarr is deployed with storage."""
    status = juju.status()
    if "radarr" in status.apps:
        return
    deploy_radarr_charm(juju, charm_path)


@pytest.fixture(scope="module")
def credentials(juju: jubilant.Juju, radarr_deployed: None) -> ArrCredentials:
    """Get radarr credentials after deployment."""
    creds = get_radarr_credentials(juju)
    assert creds is not None, "Failed to retrieve radarr credentials"
    return creds


@pytest.fixture(scope="session")
def prowlarr_charm_path() -> Path:
    """Pack prowlarr charm for integration testing."""
    if env_path := os.environ.get("PROWLARR_CHARM_PATH"):
        return Path(env_path)
    return pack_prowlarr_charm()


@pytest.fixture(scope="module")
def prowlarr_deployed(
    juju: jubilant.Juju, prowlarr_charm_path: Path, storage_deployed: None
) -> None:
    """Ensure prowlarr is deployed with storage."""
    status = juju.status()
    if "prowlarr" in status.apps:
        return
    deploy_prowlarr_charm(juju, prowlarr_charm_path)
