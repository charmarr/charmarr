# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for unit tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Container, Context, Exec

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from charm import QBittorrentCharm

QBITTORRENT_CONTAINER = Container(
    name="qbittorrent",
    can_connect=True,
    execs={Exec(["chown", "-R", "1000:1000", "/config/qBittorrent"])},
)


@pytest.fixture
def ctx() -> Context[QBittorrentCharm]:
    """Create a testing context for QBittorrentCharm."""
    return Context(QBittorrentCharm)


@pytest.fixture
def mock_k8s():
    """Create a mock K8sResourceManager."""
    with patch("charm.K8sResourceManager") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance
