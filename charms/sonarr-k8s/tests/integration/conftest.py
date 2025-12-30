# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for sonarr-k8s integration tests."""

import os
from pathlib import Path

import jubilant
import pytest

from charmarr_lib.testing import ArrCredentials
from charmarr_lib.testing.steps.storage import deploy_storage_from_charmhub
from tests.integration.helpers import (
    deploy_sonarr_charm,
    get_sonarr_credentials,
    pack_sonarr_charm,
)

pytest_plugins = [
    "charmarr_lib.testing.steps.storage",
    "charmarr_lib.testing.steps.arr",
    "charmarr_lib.testing.steps.mesh",
    "tests.integration.steps.sonarr_steps",
]


@pytest.fixture(scope="session")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_sonarr_charm()


@pytest.fixture(scope="module")
def storage_deployed(juju: jubilant.Juju) -> None:
    """Ensure charmarr-storage is deployed."""
    deploy_storage_from_charmhub(juju)


@pytest.fixture(scope="module")
def sonarr_deployed(juju: jubilant.Juju, charm_path: Path, storage_deployed: None) -> None:
    """Ensure sonarr is deployed with storage."""
    status = juju.status()
    if "sonarr" in status.apps:
        return
    deploy_sonarr_charm(juju, charm_path)


@pytest.fixture(scope="module")
def credentials(juju: jubilant.Juju, sonarr_deployed: None) -> ArrCredentials:
    """Get sonarr credentials after deployment."""
    creds = get_sonarr_credentials(juju)
    assert creds is not None, "Failed to retrieve sonarr credentials"
    return creds
