# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for unit tests."""

from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Container, Context, Exec

from charm import RadarrCharm

RADARR_CONTAINER = Container(
    name="radarr",
    can_connect=True,
    execs={Exec(["chown", "-R", "1000:1000", "/config"])},
)


@pytest.fixture
def ctx() -> Context[RadarrCharm]:
    """Create a testing context for RadarrCharm."""
    return Context(RadarrCharm)


@pytest.fixture
def mock_k8s():
    """Create a mock K8sResourceManager."""
    with patch("charm.K8sResourceManager") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance
