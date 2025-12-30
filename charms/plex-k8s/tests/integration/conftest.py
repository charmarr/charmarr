# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for plex-k8s integration tests."""

import os
from pathlib import Path

import jubilant
import pytest

from charmarr_lib.testing.steps.storage import deploy_storage_from_charmhub
from tests.integration.helpers import deploy_plex_charm, pack_plex_charm

pytest_plugins = [
    "charmarr_lib.testing.steps.storage",
    "charmarr_lib.testing.steps.mesh",
    "tests.integration.steps.plex_steps",
]


@pytest.fixture(scope="session")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_plex_charm()


@pytest.fixture(scope="module")
def storage_deployed(juju: jubilant.Juju) -> None:
    """Ensure charmarr-storage is deployed."""
    deploy_storage_from_charmhub(juju)


@pytest.fixture(scope="module")
def plex_deployed(juju: jubilant.Juju, charm_path: Path, storage_deployed: None) -> None:
    """Ensure plex is deployed with storage."""
    status = juju.status()
    if "plex" in status.apps:
        return
    deploy_plex_charm(juju, charm_path)
