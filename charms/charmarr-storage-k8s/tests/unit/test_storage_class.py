# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for storage-class backend PVC management."""

import ops
from conftest import make_api_error_404, make_pvc
from ops.testing import State


def test_creates_pvc_when_missing(ctx, mock_k8s):
    """Leader creates PVC when it doesn't exist."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={"backend-type": "storage-class", "storage-class": "local-path"},
        ),
    )

    mock_k8s.apply.assert_called_once()
    applied_pvc = mock_k8s.apply.call_args[0][0]
    assert applied_pvc.metadata.name == "charmarr-shared-media"
    assert applied_pvc.spec.storageClassName == "local-path"
    assert state.unit_status == ops.MaintenanceStatus("Creating PVC")


def test_pvc_pending_status(ctx, mock_k8s):
    """Shows active status when PVC is pending (WaitForFirstConsumer is expected)."""
    mock_k8s.get.return_value = make_pvc("Pending")

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={"backend-type": "storage-class", "storage-class": "local-path"},
        ),
    )

    assert state.unit_status == ops.ActiveStatus()


def test_pvc_bound_status(ctx, mock_k8s):
    """Shows active status when PVC is bound."""
    mock_k8s.get.return_value = make_pvc("Bound")

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={"backend-type": "storage-class", "storage-class": "local-path"},
        ),
    )

    assert state.unit_status == ops.ActiveStatus()


def test_pvc_lost_status(ctx, mock_k8s):
    """Shows blocked status when PVC is lost."""
    mock_k8s.get.return_value = make_pvc("Lost")

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={"backend-type": "storage-class", "storage-class": "local-path"},
        ),
    )

    assert state.unit_status == ops.BlockedStatus("PVC lost. Check storage backend")


def test_pvc_created_with_custom_size(ctx, mock_k8s):
    """PVC is created with custom size from config."""
    mock_k8s.get.side_effect = make_api_error_404()

    ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "storage-class",
                "storage-class": "local-path",
                "size": "2Ti",
            },
        ),
    )

    applied_pvc = mock_k8s.apply.call_args[0][0]
    assert applied_pvc.spec.resources.requests["storage"] == "2Ti"


def test_pvc_created_with_custom_access_mode(ctx, mock_k8s):
    """PVC is created with custom access mode from config."""
    mock_k8s.get.side_effect = make_api_error_404()

    ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "storage-class",
                "storage-class": "local-path",
                "access-mode": "ReadWriteOnce",
            },
        ),
    )

    applied_pvc = mock_k8s.apply.call_args[0][0]
    assert applied_pvc.spec.accessModes == ["ReadWriteOnce"]


def test_pvc_size_updated_when_changed(ctx, mock_k8s):
    """PVC size is updated when config requests larger size."""
    mock_k8s.get.return_value = make_pvc("Bound", size="100Gi")

    ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "storage-class",
                "storage-class": "local-path",
                "size": "200Gi",
            },
        ),
    )

    mock_k8s.patch.assert_called_once()
    patch_data = mock_k8s.patch.call_args[0][2]
    assert patch_data["spec"]["resources"]["requests"]["storage"] == "200Gi"


def test_pvc_size_not_updated_when_same(ctx, mock_k8s):
    """PVC is not patched when size is unchanged."""
    mock_k8s.get.return_value = make_pvc("Bound", size="100Gi")

    ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            config={
                "backend-type": "storage-class",
                "storage-class": "local-path",
                "size": "100Gi",
            },
        ),
    )

    mock_k8s.patch.assert_not_called()
