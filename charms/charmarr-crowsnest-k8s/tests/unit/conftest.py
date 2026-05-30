# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for charmarr-crowsnest unit tests."""

import sys
from pathlib import Path

import pytest
from ops.testing import Context

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from charm import CharmarrCrowsnestCharm


@pytest.fixture
def ctx() -> Context[CharmarrCrowsnestCharm]:
    """Scenario context for the crowsnest charm."""
    return Context(CharmarrCrowsnestCharm)
