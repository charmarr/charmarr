# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for backend-type change validation."""

import ops
from conftest import make_api_error_404, make_nfs_pv, make_nfs_pvc, make_pvc
from ops.testing import State


def test_backend_change_allowed_when_no_pvc(ctx, mock_k8s):
    """Backend-type can be set when no PVC exists."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={"backend-type": "storage-class", "storage-class": "local-path"},
        ),
    )

    assert state.unit_status == ops.MaintenanceStatus("Creating PVC")


def test_blocked_changing_from_storage_class_to_nfs(ctx, mock_k8s):
    """Charm is blocked when trying to switch from storage-class to native-nfs."""
    mock_k8s._custom_get_return = make_pvc(phase="Bound")

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "native-nfs",
                "nfs-server": "192.168.1.100",
                "nfs-path": "/mnt/media",
            },
        ),
    )

    assert state.unit_status == ops.BlockedStatus(
        "Cannot change backend from 'storage-class' to 'native-nfs'. "
        "Redeploy with required backend (WARNING: may cause data loss)."
    )


def test_blocked_changing_from_nfs_to_storage_class(ctx, mock_k8s):
    """Charm is blocked when trying to switch from native-nfs to storage-class."""

    def mock_get(resource_type, name, namespace=None):
        if resource_type.__name__ == "PersistentVolumeClaim":
            return make_nfs_pvc(phase="Bound")
        elif resource_type.__name__ == "PersistentVolume":
            return make_nfs_pv(phase="Bound")
        raise ValueError(f"Unexpected resource type: {resource_type}")

    mock_k8s._custom_get_side_effect = mock_get

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "storage-class",
                "storage-class": "local-path",
            },
        ),
    )

    assert state.unit_status == ops.BlockedStatus(
        "Cannot change backend from 'native-nfs' to 'storage-class'. "
        "Redeploy with required backend (WARNING: may cause data loss)."
    )


def test_same_backend_type_not_blocked(ctx, mock_k8s):
    """Charm is not blocked when backend-type matches existing PVC."""
    mock_k8s._custom_get_return = make_pvc(phase="Bound")

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={"backend-type": "storage-class", "storage-class": "local-path"},
        ),
    )

    assert state.unit_status == ops.ActiveStatus()


def test_same_nfs_backend_not_blocked(ctx, mock_k8s):
    """Charm is not blocked when native-nfs backend-type matches existing PVC."""

    def mock_get(resource_type, name, namespace=None):
        if resource_type.__name__ == "PersistentVolumeClaim":
            return make_nfs_pvc(phase="Bound")
        elif resource_type.__name__ == "PersistentVolume":
            return make_nfs_pv(phase="Bound")
        raise ValueError(f"Unexpected resource type: {resource_type}")

    mock_k8s._custom_get_side_effect = mock_get

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "native-nfs",
                "nfs-server": "192.168.1.100",
                "nfs-path": "/mnt/media",
            },
        ),
    )

    assert state.unit_status == ops.ActiveStatus()


def test_reconcile_blocked_on_backend_change(ctx, mock_k8s):
    """Reconcile does not proceed when backend change is blocked."""
    mock_k8s._custom_get_return = make_pvc(phase="Bound")

    ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "native-nfs",
                "nfs-server": "192.168.1.100",
                "nfs-path": "/mnt/media",
            },
        ),
    )

    mock_k8s.apply.assert_not_called()
