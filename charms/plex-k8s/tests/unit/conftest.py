# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for unit tests."""

from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Container, Context, Exec

from charm import PlexCharm

PLEX_CONTAINER = Container(
    name="plex",
    can_connect=True,
    execs={
        Exec(["chown", "-R", "1000:1000", "/config"]),
        Exec(["mkdir", "-p", "/config/Library/Application Support"]),
        Exec(["mkdir", "-p", "/run/plex-temp"]),
        Exec(["chown", "1000:1000", "/run/plex-temp"]),
    },
)


@pytest.fixture
def ctx() -> Context[PlexCharm]:
    """Create a testing context for PlexCharm."""
    return Context(PlexCharm)


@pytest.fixture
def mock_k8s():
    """Create a mock K8sResourceManager."""
    with patch("charm.K8sResourceManager") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance
