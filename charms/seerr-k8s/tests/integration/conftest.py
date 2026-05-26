# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for seerr-k8s integration tests."""

import os
from pathlib import Path

import jubilant
import pytest

from tests.integration.helpers import deploy_seerr_charm, pack_seerr_charm

pytest_plugins = [
    "charmarr_lib.testing.steps.arr",
    "tests.integration.steps.seerr_steps",
]


@pytest.fixture(scope="session")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_seerr_charm()


@pytest.fixture(scope="module")
def seerr_deployed(juju: jubilant.Juju, charm_path: Path) -> None:
    """Ensure seerr is deployed."""
    status = juju.status()
    if "seerr" in status.apps:
        return
    deploy_seerr_charm(juju, charm_path)
