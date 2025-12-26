# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for qbittorrent-k8s integration tests."""

import json
import logging
from pathlib import Path

import jubilant
from pydantic import BaseModel
from pytest_jubilant import pack

from _qbittorrent import CREDENTIALS_SECRET_LABEL
from charmarr_lib.testing import get_oci_resources, wait_for_active_idle

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


class Credentials(BaseModel):
    """Credentials retrieved from a Juju secret."""

    username: str
    password: str
    secret_id: str


def pack_qbittorrent_charm() -> Path:
    """Pack the qbittorrent charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_qbittorrent_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy qbittorrent charm with storage relation."""
    juju.deploy(
        str(charm_path),
        app="qbittorrent",
        trust=True,
        resources=get_oci_resources(CHARM_DIR),
    )
    juju.integrate("qbittorrent:media-storage", "charmarr-storage:media-storage")
    wait_for_active_idle(juju)


def get_qbittorrent_credentials(juju: jubilant.Juju) -> Credentials | None:
    """Get credentials from qbittorrent's app-owned secret."""
    try:
        output = juju.cli("list-secrets", "--format=json")
        secrets = json.loads(output)

        for secret_id, info in secrets.items():
            if (
                info.get("owner") == "qbittorrent"
                and info.get("label") == CREDENTIALS_SECRET_LABEL
            ):
                content_output = juju.cli("show-secret", secret_id, "--reveal", "--format=json")
                content_data = json.loads(content_output)
                content = content_data[secret_id]["content"]["Data"]
                return Credentials(
                    username=content.get("username", ""),
                    password=content.get("password", ""),
                    secret_id=secret_id,
                )
        return None
    except Exception as e:
        logger.warning("Failed to get credentials: %s", e)
        return None
