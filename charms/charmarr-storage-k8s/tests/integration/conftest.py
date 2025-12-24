# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for charmarr-storage-k8s integration tests."""

import logging
import shutil
import subprocess
from collections.abc import Generator

import jubilant
import pytest

from charmarr_lib.testing import deploy_multimeter, wait_for_active_idle

logger = logging.getLogger(__name__)

pytest_plugins = [
    "tests.integration.steps.common_steps",
    "tests.integration.steps.storage_class_steps",
    "tests.integration.steps.native_nfs_steps",
]


def _nfs_common_available() -> bool:
    """Check if nfs-common package is installed."""
    if shutil.which("mount.nfs"):
        return True
    result = subprocess.run(
        ["dpkg", "-l", "nfs-common"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@pytest.fixture(scope="module")
def nfs_server_ip(juju: jubilant.Juju) -> Generator[str, None, None]:
    """Deploy mock NFS server via multimeter action and return its ClusterIP.

    The NFS server is deployed before tests and cleaned up after.
    Skips test if nfs-common is not installed.
    """
    if not _nfs_common_available():
        pytest.skip("nfs-common not installed - NFS tests require NFS client support")

    status = juju.status()
    if "charmarr-multimeter" not in status.apps:
        deploy_multimeter(juju)
        wait_for_active_idle(juju)

    try:
        result = juju.run("charmarr-multimeter/0", "deploy-nfs-server")
        ip = result.results["nfs-server-ip"]
        logger.info("NFS server deployed at %s", ip)
    except Exception as e:
        logger.warning("NFS server deployment failed: %s", e)
        pytest.skip(f"NFS server deployment failed: {e}")

    yield ip

    try:
        juju.run("charmarr-multimeter/0", "cleanup-nfs-server")
    except Exception as e:
        logger.warning("NFS server cleanup failed: %s", e)
