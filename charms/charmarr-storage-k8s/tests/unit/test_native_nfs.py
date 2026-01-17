# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for native-nfs backend."""

import ops
from conftest import make_api_error_404, make_nfs_pv, make_nfs_pvc
from lightkube.resources.core_v1 import PersistentVolume, PersistentVolumeClaim
from ops.testing import State


def _nfs_config() -> dict:
    """Return standard native-nfs config."""
    return {
        "backend-type": "native-nfs",
        "nfs-server": "192.168.1.100",
        "nfs-path": "/mnt/media",
    }


def test_creates_pv_when_missing(ctx, mock_k8s):
    """Leader creates NFS PV when it doesn't exist."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_nfs_config()),
    )

    assert mock_k8s.apply.call_count >= 1
    applied_pv = mock_k8s.apply.call_args_list[0][0][0]
    assert isinstance(applied_pv, PersistentVolume)
    assert applied_pv.metadata.name == "charmarr-shared-media-pv"
    assert applied_pv.spec.nfs.server == "192.168.1.100"
    assert applied_pv.spec.nfs.path == "/mnt/media"
    assert applied_pv.spec.persistentVolumeReclaimPolicy == "Retain"
    assert state.unit_status == ops.MaintenanceStatus("Creating NFS PV")


def test_creates_pvc_after_pv_exists(ctx, mock_k8s):
    """Leader creates PVC once PV exists."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Available")
        raise make_api_error_404()

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_nfs_config()),
    )

    applied_pvc = mock_k8s.apply.call_args[0][0]
    assert isinstance(applied_pvc, PersistentVolumeClaim)
    assert applied_pvc.metadata.name == "charmarr-shared-media"
    assert applied_pvc.spec.volumeName == "charmarr-shared-media-pv"
    assert applied_pvc.spec.storageClassName == ""
    assert state.unit_status == ops.MaintenanceStatus("Creating PVC")


def test_pv_created_with_custom_size(ctx, mock_k8s):
    """NFS PV is created with custom size from config."""
    mock_k8s.get.side_effect = make_api_error_404()

    config = _nfs_config()
    config["size"] = "2Ti"

    ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=config),
    )

    applied_pv = mock_k8s.apply.call_args_list[0][0][0]
    assert applied_pv.spec.capacity["storage"] == "2Ti"


def test_pvc_bound_status(ctx, mock_k8s):
    """Shows active status when both PV and PVC are bound."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Bound")
        return make_nfs_pvc("Bound")

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_nfs_config()),
    )

    assert state.unit_status == ops.ActiveStatus()


def test_pvc_pending_status(ctx, mock_k8s):
    """Shows active status when PVC is pending (WaitForFirstConsumer is expected)."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Available")
        return make_nfs_pvc("Pending")

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_nfs_config()),
    )

    assert state.unit_status == ops.ActiveStatus()


def test_pv_failed_status(ctx, mock_k8s):
    """Shows blocked status when PV is in failed state."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Failed")
        return make_nfs_pvc("Pending")

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_nfs_config()),
    )

    assert state.unit_status == ops.BlockedStatus("NFS PV failed. Check storage backend")


def test_pvc_lost_status(ctx, mock_k8s):
    """Shows blocked status when PVC is lost."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Bound")
        return make_nfs_pvc("Lost")

    mock_k8s._custom_get_side_effect = get_side_effect

    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_nfs_config()),
    )

    assert state.unit_status == ops.BlockedStatus("PVC lost. Check NFS backend")


def test_does_not_recreate_existing_pv(ctx, mock_k8s):
    """PV is not recreated if it already exists."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Bound")
        return make_nfs_pvc("Bound")

    mock_k8s._custom_get_side_effect = get_side_effect

    ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=_nfs_config()),
    )

    for call in mock_k8s.apply.call_args_list:
        resource = call[0][0]
        assert not isinstance(resource, (PersistentVolume, PersistentVolumeClaim)), (
            f"PV/PVC should not be recreated, but {type(resource).__name__} was applied"
        )


def test_access_mode_always_rwx(ctx, mock_k8s):
    """NFS backend always uses ReadWriteMany access mode."""
    mock_k8s.get.side_effect = make_api_error_404()

    config = _nfs_config()
    config["access-mode"] = "ReadWriteOnce"

    ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=config),
    )

    applied_pv = mock_k8s.apply.call_args_list[0][0][0]
    assert applied_pv.spec.accessModes == ["ReadWriteMany"]


def test_pv_size_updated_when_changed(ctx, mock_k8s):
    """PV size is updated when config size changes."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Bound", size="100Gi")
        return make_nfs_pvc("Bound", size="100Gi")

    mock_k8s._custom_get_side_effect = get_side_effect

    config = _nfs_config()
    config["size"] = "2Ti"

    ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=config),
    )

    assert mock_k8s.apply.call_count >= 1
    applied_pv = mock_k8s.apply.call_args_list[0][0][0]
    assert isinstance(applied_pv, PersistentVolume)
    assert applied_pv.spec.capacity["storage"] == "2Ti"


def test_pvc_size_not_patched_for_native_nfs(ctx, mock_k8s):
    """PVC size is not patched for native-nfs (K8s doesn't support static PVC resize)."""

    def get_side_effect(resource_type, name, namespace=None):
        if resource_type == PersistentVolume:
            return make_nfs_pv("Bound", size="100Gi")
        return make_nfs_pvc("Bound", size="100Gi")

    mock_k8s._custom_get_side_effect = get_side_effect

    config = _nfs_config()
    config["size"] = "2Ti"

    ctx.run(
        ctx.on.config_changed(),
        State(leader=True, config=config),
    )

    # PVC patch should not be called - K8s doesn't support resizing static PVCs
    # PV is updated via apply, not patch
    mock_k8s.patch.assert_not_called()
