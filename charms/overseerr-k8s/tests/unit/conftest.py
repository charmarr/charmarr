# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for unit tests."""

from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Container, Context, Exec

from charm import OverseerrCharm

OVERSEERR_CONTAINER = Container(
    name="overseerr",
    can_connect=True,
    execs={
        Exec(["chown", "-R", "1000:1000", "/config"]),
    },
)


@pytest.fixture
def ctx() -> Context[OverseerrCharm]:
    """Create a testing context for OverseerrCharm."""
    return Context(OverseerrCharm)


@pytest.fixture
def mock_httpx():
    """Mock httpx.Client for API calls."""
    with patch("_overseerr._api.httpx.Client") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_class.return_value.__exit__ = MagicMock(return_value=None)
        yield mock_instance
