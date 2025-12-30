# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for flaresolverr-k8s integration tests."""

import logging
from pathlib import Path

import jubilant
from pytest_jubilant import pack

from charmarr_lib.testing import get_oci_resources, wait_for_active_idle

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


def pack_flaresolverr_charm() -> Path:
    """Pack the flaresolverr charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_flaresolverr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy flaresolverr charm."""
    juju.deploy(
        str(charm_path),
        app="flaresolverr",
        trust=True,
        resources=get_oci_resources(CHARM_DIR),
    )
    wait_for_active_idle(juju)
