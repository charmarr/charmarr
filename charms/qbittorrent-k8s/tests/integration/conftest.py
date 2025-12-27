# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for qbittorrent-k8s integration tests."""

import os
from pathlib import Path

import jubilant
import pytest

from charmarr_lib.testing import vpn_creds_available, wait_for_active_idle
from tests.integration.helpers import Credentials, deploy_qbittorrent_charm, pack_qbittorrent_charm

pytest_plugins = [
    "charmarr_lib.testing.steps.multimeter",
    "charmarr_lib.testing.steps.storage",
    "charmarr_lib.testing.steps.gluetun",
    "charmarr_lib.testing.steps.mesh",
    "charmarr_lib.testing.steps.download_client",
    "tests.integration.steps.qbittorrent_steps",
]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark VPN tests as xfail if credentials not available."""
    if vpn_creds_available():
        return

    for item in items:
        if "vpn" in str(item.fspath):
            item.add_marker(
                pytest.mark.xfail(
                    reason="WIREGUARD_PRIVATE_KEY environment variable required",
                    run=False,
                )
            )


@pytest.fixture(scope="module")
def charm_path() -> Path:
    """Get charm path from CI or pack locally."""
    if env_path := os.environ.get("CHARM_PATH"):
        return Path(env_path)
    return pack_qbittorrent_charm()


@pytest.fixture(scope="module")
def qbittorrent_deployed(juju: jubilant.Juju, charm_path: Path, storage_deployed: None) -> None:
    """Ensure qbittorrent is deployed with storage relation."""
    status = juju.status()
    if "qbittorrent" in status.apps:
        return
    deploy_qbittorrent_charm(juju, charm_path)


@pytest.fixture(scope="module")
def storage_deployed(juju: jubilant.Juju) -> None:
    """Ensure charmarr-storage is deployed."""
    from charmarr_lib.testing.steps.storage import deploy_storage_from_charmhub

    deploy_storage_from_charmhub(juju)


@pytest.fixture(scope="module")
def credentials(juju: jubilant.Juju, qbittorrent_deployed: None) -> Credentials:
    """Get qbittorrent credentials after deployment."""
    from tests.integration.helpers import get_qbittorrent_credentials

    creds = get_qbittorrent_credentials(juju)
    assert creds is not None, "Failed to retrieve qbittorrent credentials"
    return creds


@pytest.fixture(scope="module")
def multimeter_related(juju: jubilant.Juju, qbittorrent_deployed: None) -> None:
    """Ensure multimeter is related to qbittorrent via download-client."""
    from charmarr_lib.testing import deploy_multimeter

    status = juju.status()
    if "charmarr-multimeter" not in status.apps:
        deploy_multimeter(juju)
        wait_for_active_idle(juju)

    app = status.apps.get("charmarr-multimeter")
    if not app or "download-client" not in app.relations:
        juju.integrate("charmarr-multimeter:download-client", "qbittorrent:download-client")
        wait_for_active_idle(juju)
