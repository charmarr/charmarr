# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for native-nfs backend tests."""

from typing import Any

import jubilant
from pytest_bdd import parsers, then
from tenacity import retry, stop_after_attempt, wait_exponential

from tests.integration.helpers import get_pv, get_pvc


@then(parsers.parse('a PV named "{name}" should exist'))
def pv_exists(juju: jubilant.Juju, name: str):
    """Verify PV exists."""

    @retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, min=2, max=10))
    def check_exists():
        assert get_pv(juju, name) is not None, f"PV {name} not found"

    check_exists()


@then("the PV should have NFS server from config")
def pv_nfs_server_from_config(juju: jubilant.Juju, storage_config: dict[str, Any]):
    """Verify PV has the NFS server from config."""
    expected_server = storage_config["nfs-server"]
    pv = get_pv(juju, "charmarr-shared-media-pv")
    assert pv is not None
    assert pv.nfs_server == expected_server


@then(parsers.parse('the PV should have NFS server "{server}"'))
def pv_nfs_server(juju: jubilant.Juju, server: str):
    """Verify PV has the expected NFS server."""
    pv = get_pv(juju, "charmarr-shared-media-pv")
    assert pv is not None
    assert pv.nfs_server == server


@then(parsers.parse('the PV should have NFS path "{path}"'))
def pv_nfs_path(juju: jubilant.Juju, path: str):
    """Verify PV has the expected NFS path."""
    pv = get_pv(juju, "charmarr-shared-media-pv")
    assert pv is not None
    assert pv.nfs_path == path


@then(parsers.parse('the PVC should be bound to PV "{pv_name}"'))
def pvc_bound_to(juju: jubilant.Juju, pv_name: str):
    """Verify PVC is bound to the expected PV."""

    @retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, min=2, max=10))
    def check_bound():
        pvc = get_pvc(juju, juju.model, "charmarr-shared-media")
        assert pvc is not None, "PVC not found"
        assert pvc.volume_name == pv_name, f"PVC bound to {pvc.volume_name}, expected {pv_name}"

    check_bound()


@then(parsers.parse('the PVC should have access mode "{mode}"'))
def pvc_access_mode_nfs(juju: jubilant.Juju, mode: str):
    """Verify PVC has the expected access mode."""
    pvc = get_pvc(juju, juju.model, "charmarr-shared-media")
    assert pvc is not None
    assert mode in pvc.access_modes


@then(parsers.parse('the PV should have reclaim policy "{policy}"'))
def pv_reclaim_policy(juju: jubilant.Juju, policy: str):
    """Verify PV has the expected reclaim policy."""
    pv = get_pv(juju, "charmarr-shared-media-pv")
    assert pv is not None
    assert pv.reclaim_policy == policy
