# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for charmarr-multimeter unit tests."""

import sys
from pathlib import Path

import pytest
from ops.testing import Context

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from charm import CharmarrMultimeterCharm


@pytest.fixture
def ctx() -> Context[CharmarrMultimeterCharm]:
    """Create a testing context for CharmarrMultimeterCharm."""
    return Context(CharmarrMultimeterCharm)
