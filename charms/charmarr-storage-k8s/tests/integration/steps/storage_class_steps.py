# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for storage-class backend tests."""

from typing import Any

import jubilant
from pytest_bdd import parsers, then

from tests.integration.helpers import get_pvc


@then("the PVC should use the configured storage class")
def pvc_storage_class(juju: jubilant.Juju, storage_config: dict[str, Any]):
    """Verify PVC uses the configured storage class."""
    pvc = get_pvc(juju, juju.model, "charmarr-shared-media")
    assert pvc is not None
    assert pvc.storage_class == storage_config["storage-class"]


@then("the PVC should have the configured access mode")
def pvc_access_mode(juju: jubilant.Juju, storage_config: dict[str, Any]):
    """Verify PVC has the configured access mode."""
    pvc = get_pvc(juju, juju.model, "charmarr-shared-media")
    assert pvc is not None
    assert storage_config["access-mode"] in pvc.access_modes


@then("the PVC should have the configured size")
def pvc_size(juju: jubilant.Juju, storage_config: dict[str, Any]):
    """Verify PVC has the configured size."""
    pvc = get_pvc(juju, juju.model, "charmarr-shared-media")
    assert pvc is not None
    assert pvc.capacity == storage_config["size"]


@then(parsers.parse('the PVC should have requested size "{size}"'))
def pvc_requested_size(juju: jubilant.Juju, size: str):
    """Verify PVC has the expected requested size."""
    pvc = get_pvc(juju, juju.model, "charmarr-shared-media")
    assert pvc is not None
    assert pvc.capacity == size
