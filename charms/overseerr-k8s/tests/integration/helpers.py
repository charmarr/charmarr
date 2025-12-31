# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for overseerr-k8s integration tests."""

import logging
from pathlib import Path

import jubilant
from pytest_jubilant import pack

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


def pack_overseerr_charm() -> Path:
    """Pack the overseerr charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def _overseerr_waiting_for_setup(status: jubilant.Status) -> bool:
    """Check if overseerr is waiting for setup."""
    app = status.apps.get("overseerr")
    if not app:
        return False
    unit = app.units.get("overseerr/0")
    if not unit:
        return False
    return (
        unit.workload_status.current == "waiting"
        and "setup" in unit.workload_status.message.lower()
    )


def deploy_overseerr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy overseerr charm."""
    juju.deploy(
        charm_path,
        app="overseerr",
        trust=True,
        resources={"overseerr-image": "lscr.io/linuxserver/overseerr:latest"},
    )
    juju.wait(_overseerr_waiting_for_setup, delay=5, timeout=60 * 10)
