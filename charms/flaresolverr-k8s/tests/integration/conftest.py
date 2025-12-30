# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for flaresolverr-k8s integration tests."""

import os
from pathlib import Path

import jubilant
import pytest

from tests.integration.helpers import deploy_flaresolverr_charm, pack_flaresolverr_charm

pytest_plugins = [
    "charmarr_lib.testing.steps.multimeter",
    "charmarr_lib.testing.steps.mesh",
    "tests.integration.steps.flaresolverr_steps",
]


@pytest.fixture(scope="module")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_flaresolverr_charm()


@pytest.fixture(scope="module")
def flaresolverr_deployed(juju: jubilant.Juju, charm_path: Path) -> None:
    """Ensure flaresolverr is deployed."""
    status = juju.status()
    if "flaresolverr" in status.apps:
        return
    deploy_flaresolverr_charm(juju, charm_path)
