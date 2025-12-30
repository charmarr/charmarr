# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for radarr-k8s integration tests."""

import logging
from pathlib import Path

import jubilant
from pytest_jubilant import pack

from _radarr import API_KEY_SECRET_LABEL, WEBUI_PORT
from charmarr_lib.testing import ArrCredentials, deploy_arr_charm, get_arr_credentials

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent
CHARMS_DIR = CHARM_DIR.parent


def pack_radarr_charm() -> Path:
    """Pack the radarr charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_radarr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy radarr charm with storage."""
    deploy_arr_charm(juju, charm_path, "radarr", CHARM_DIR, with_storage=True)


def get_radarr_credentials(juju: jubilant.Juju) -> ArrCredentials | None:
    """Get API credentials from radarr's app-owned secret."""
    creds = get_arr_credentials(juju, "radarr", API_KEY_SECRET_LABEL)
    if creds:
        creds.base_url = f"http://radarr:{WEBUI_PORT}/radarr"
    return creds


def pack_prowlarr_charm() -> Path:
    """Pack the prowlarr charm and return path to .charm file."""
    prowlarr_dir = CHARMS_DIR / "prowlarr-k8s"
    logger.info("Packing prowlarr charm from %s", prowlarr_dir)
    return pack(prowlarr_dir)


def deploy_prowlarr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy prowlarr charm (no storage required)."""
    prowlarr_dir = CHARMS_DIR / "prowlarr-k8s"
    deploy_arr_charm(juju, charm_path, "prowlarr", prowlarr_dir, with_storage=False)
