# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions for seerr-k8s integration tests."""

import logging
from pathlib import Path

import jubilant
from pytest_jubilant import pack

from charmarr_lib.testing import get_oci_resources

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


def pack_seerr_charm() -> Path:
    """Pack the seerr charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def _seerr_waiting_for_setup(status: jubilant.Status) -> bool:
    """Check if seerr is waiting for setup."""
    app = status.apps.get("seerr")
    if not app:
        return False
    unit = app.units.get("seerr/0")
    if not unit:
        return False
    return (
        unit.workload_status.current == "waiting"
        and "setup" in unit.workload_status.message.lower()
    )


def deploy_seerr_charm(juju: jubilant.Juju, charm_path: Path) -> None:
    """Deploy seerr charm."""
    juju.deploy(
        charm_path,
        app="seerr",
        trust=True,
        resources=get_oci_resources(CHARM_DIR),
    )
    juju.wait(_seerr_waiting_for_setup, delay=5, timeout=60 * 10)
