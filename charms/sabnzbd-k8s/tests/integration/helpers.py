# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for sabnzbd-k8s integration tests."""

import json
import logging
from pathlib import Path

import jubilant
from pydantic import BaseModel
from pytest_jubilant import pack

from _sabnzbd import API_KEY_SECRET_LABEL
from charmarr_lib.testing import get_oci_resources, wait_for_active_idle

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


class ApiKey(BaseModel):
    """API key retrieved from a Juju secret."""

    api_key: str
    secret_id: str


def pack_sabnzbd_charm() -> Path:
    """Pack the sabnzbd charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_sabnzbd_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy sabnzbd charm with storage relation."""
    juju.deploy(
        str(charm_path),
        app="sabnzbd",
        trust=True,
        resources=get_oci_resources(CHARM_DIR),
    )
    juju.integrate("sabnzbd:media-storage", "charmarr-storage:media-storage")
    wait_for_active_idle(juju)


def get_sabnzbd_api_key(juju: jubilant.Juju) -> ApiKey | None:
    """Get API key from sabnzbd's app-owned secret."""
    try:
        output = juju.cli("list-secrets", "--format=json")
        secrets = json.loads(output)

        for secret_id, info in secrets.items():
            if info.get("owner") == "sabnzbd" and info.get("label") == API_KEY_SECRET_LABEL:
                content_output = juju.cli("show-secret", secret_id, "--reveal", "--format=json")
                content_data = json.loads(content_output)
                content = content_data[secret_id]["content"]["Data"]
                return ApiKey(
                    api_key=content.get("api-key", ""),
                    secret_id=secret_id,
                )
        return None
    except Exception as e:
        logger.warning("Failed to get API key: %s", e)
        return None
