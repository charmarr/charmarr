# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for prowlarr-k8s integration tests."""

import logging
from pathlib import Path

import jubilant
from pytest_jubilant import pack

from _prowlarr import API_KEY_SECRET_LABEL, WEBUI_PORT
from charmarr_lib.testing import (
    ArrCredentials,
    deploy_arr_charm,
    get_arr_credentials,
)

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent
CHARMS_DIR = CHARM_DIR.parent


def pack_prowlarr_charm() -> Path:
    """Pack the prowlarr charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_prowlarr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy prowlarr charm (no storage required)."""
    deploy_arr_charm(juju, charm_path, "prowlarr", CHARM_DIR, with_storage=False)


def get_prowlarr_credentials(juju: jubilant.Juju) -> ArrCredentials | None:
    """Get API credentials from prowlarr's app-owned secret."""
    creds = get_arr_credentials(juju, "prowlarr", API_KEY_SECRET_LABEL)
    if creds:
        creds.base_url = f"http://prowlarr:{WEBUI_PORT}/prowlarr"
    return creds


def deploy_radarr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy radarr charm with storage relation."""
    radarr_dir = CHARMS_DIR / "radarr-k8s"
    deploy_arr_charm(juju, charm_path, "radarr", radarr_dir, with_storage=True)
