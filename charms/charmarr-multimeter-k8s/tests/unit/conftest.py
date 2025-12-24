# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for charmarr-multimeter unit tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Context

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from charm import CharmarrMultimeterCharm


@pytest.fixture(autouse=True)
def mock_k8s():
    """Mock K8s operations that require cluster access."""
    with (
        patch("charm.reconcile_storage_volume") as mock_reconcile,
        patch("charm.K8sResourceManager") as mock_k8s_manager,
        patch("charm.deploy_nfs_server") as mock_deploy_nfs,
        patch("charm.cleanup_nfs_server") as mock_cleanup_nfs,
        patch("charm.reconcile_gateway_client") as mock_gw_client,
    ):
        mock_k8s_manager.return_value = MagicMock()
        mock_reconcile.return_value = None
        mock_deploy_nfs.return_value = "10.152.183.100"
        mock_cleanup_nfs.return_value = None
        mock_gw_client.return_value = None
        yield mock_k8s_manager


@pytest.fixture
def ctx() -> Context[CharmarrMultimeterCharm]:
    """Create a testing context for CharmarrMultimeterCharm."""
    return Context(CharmarrMultimeterCharm)
