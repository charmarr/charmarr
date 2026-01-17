# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for hostpath backend tests."""

from typing import Any

import jubilant
from pytest_bdd import then

from tests.integration.helpers import get_pv


@then("the PV should have hostPath from config")
def pv_hostpath_from_config(juju: jubilant.Juju, storage_config: dict[str, Any]):
    """Verify PV has the hostPath from config."""
    expected_path = storage_config["hostpath"]
    pv = get_pv(juju, "charmarr-shared-media-pv")
    assert pv is not None
    assert pv.hostpath == expected_path
