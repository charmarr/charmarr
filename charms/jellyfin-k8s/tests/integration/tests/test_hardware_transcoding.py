# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Test runner for hardware transcoding feature."""

import pytest
from pytest_bdd import scenarios

# CI runners typically lack /dev/dri - pod won't schedule without GPU
pytestmark = pytest.mark.xfail(reason="Requires /dev/dri on host", strict=False)

scenarios("../features/hardware_transcoding.feature")
