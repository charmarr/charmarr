# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for hostpath backend."""

import ops
from conftest import make_api_error_404, make_hostpath_pv, make_hostpath_pvc
from lightkube.resources.core_v1 import PersistentVolume, PersistentVolumeClaim
from ops.testing import State


def _hostpath_config() -> dict:
    """Return standard hostpath config."""
    return {
        "backend-type": "hostpath",
        "hostpath": "/media",
    }


def test_creates_pv_when_missing(ctx, mock_k8s):
    """Leader creates hostPath PV when it doesn't exist."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_hostpath_config()),
    )

    assert mock_k8s.apply.call_count >= 1
    applied_pv = mock_k8s.apply.call_args_list[0][0][0]
    assert isinstance(applied_pv, PersistentVolume)
    assert applied_pv.metadata.name == "charmarr-shared-media-pv"
    assert applied_pv.spec.hostPath.path == "/media"
    assert applied_pv.spec.hostPath.type == "Directory"
    assert applied_pv.spec.persistentVolumeReclaimPolicy == "Retain"
    assert state.unit_status == ops.MaintenanceStatus("Creating hostPath PV")


def test_creates_pvc_after_pv_exists(ctx, mock_k8s):
    """Leader creates PVC once PV exists."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_hostpath_pv("Available")
        raise make_api_error_404()

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_hostpath_config()),
    )

    applied_pvc = mock_k8s.apply.call_args[0][0]
    assert isinstance(applied_pvc, PersistentVolumeClaim)
    assert applied_pvc.metadata.name == "charmarr-shared-media"
    assert applied_pvc.spec.volumeName == "charmarr-shared-media-pv"
    assert applied_pvc.spec.storageClassName == ""
    assert state.unit_status == ops.MaintenanceStatus("Creating PVC")


def test_active_when_pvc_bound(ctx, mock_k8s):
    """Shows active status when PVC is bound."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_hostpath_pv("Bound")
        return make_hostpath_pvc("Bound")

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_hostpath_config()),
    )

    assert state.unit_status == ops.ActiveStatus()


def test_blocked_without_hostpath_config(ctx, mock_k8s):
    """Shows blocked when hostpath is not configured."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config={"backend-type": "hostpath"}),
    )

    assert state.unit_status == ops.BlockedStatus("hostpath not configured")


def test_pv_failed_status(ctx, mock_k8s):
    """Shows blocked status when PV is failed."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_hostpath_pv("Failed")
        return make_hostpath_pvc("Pending")

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_hostpath_config()),
    )

    assert state.unit_status == ops.BlockedStatus("hostPath PV failed. Check storage backend")


def test_pvc_lost_status(ctx, mock_k8s):
    """Shows blocked status when PVC is lost."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_hostpath_pv("Bound")
        return make_hostpath_pvc("Lost")

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_hostpath_config()),
    )

    assert state.unit_status == ops.BlockedStatus("PVC lost. Check hostPath backend")
