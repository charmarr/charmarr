# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for plex-k8s integration tests."""

import logging
from pathlib import Path

import jubilant
from pytest_jubilant import pack

from charmarr_lib.testing import get_oci_resources, wait_for_app_status

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


def pack_plex_charm() -> Path:
    """Pack the plex charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_plex_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy plex charm with storage relation."""
    status = juju.status()
    if "plex" in status.apps:
        return

    resources = get_oci_resources(CHARM_DIR)
    juju.deploy(charm_path, app="plex", trust=True, resources=resources)
    juju.integrate("plex:media-storage", "charmarr-storage:media-storage")
    wait_for_app_status(juju, "plex", "blocked", message_contains="claim-token")
