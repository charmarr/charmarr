# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for sonarr-k8s integration tests."""

import logging
from pathlib import Path

import jubilant
from pytest_jubilant import pack

from _sonarr import API_KEY_SECRET_LABEL, WEBUI_PORT
from charmarr_lib.testing import ArrCredentials, deploy_arr_charm, get_arr_credentials

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent
CHARMS_DIR = CHARM_DIR.parent


def pack_sonarr_charm() -> Path:
    """Pack the sonarr charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_sonarr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy sonarr charm with storage."""
    deploy_arr_charm(juju, charm_path, "sonarr", CHARM_DIR, with_storage=True)


def get_sonarr_credentials(juju: jubilant.Juju) -> ArrCredentials | None:
    """Get API credentials from sonarr's app-owned secret."""
    creds = get_arr_credentials(juju, "sonarr", API_KEY_SECRET_LABEL)
    if creds:
        creds.base_url = f"http://sonarr:{WEBUI_PORT}/sonarr"
    return creds
