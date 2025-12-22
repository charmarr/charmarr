# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for CharmarrStorageCharm - config validation."""

from unittest.mock import patch

import ops
from conftest import make_api_error_404
from ops.testing import State


def test_blocked_without_backend_type(ctx):
    """Charm is blocked when backend-type is not configured."""
    state = ctx.run(ctx.on.config_changed(), State())
    assert state.unit_status == ops.BlockedStatus("backend-type not configured")


def test_blocked_with_invalid_backend_type(ctx):
    """Charm is blocked when backend-type is invalid."""
    state = ctx.run(ctx.on.config_changed(), State(config={"backend-type": "invalid"}))
    assert state.unit_status == ops.BlockedStatus(
        "Invalid backend-type: invalid. Use 'storage-class' or 'native-nfs'"
    )


def test_blocked_storage_class_without_class_name(ctx, mock_k8s):
    """Charm is blocked when storage-class backend lacks storage-class config."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(config={"backend-type": "storage-class"}),
    )
    assert state.unit_status == ops.BlockedStatus("storage-class not configured")


def test_blocked_native_nfs_without_server(ctx, mock_k8s):
    """Charm is blocked when native-nfs backend lacks nfs-server."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(config={"backend-type": "native-nfs", "nfs-path": "/mnt/media"}),
    )
    assert state.unit_status == ops.BlockedStatus("nfs-server not configured")


def test_blocked_native_nfs_without_path(ctx, mock_k8s):
    """Charm is blocked when native-nfs backend lacks nfs-path."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = ctx.run(
        ctx.on.config_changed(),
        State(config={"backend-type": "native-nfs", "nfs-server": "192.168.1.100"}),
    )
    assert state.unit_status == ops.BlockedStatus("nfs-path not configured")


def test_non_leader_standby_status(ctx):
    """Non-leader unit shows standby status."""
    with patch("charm.K8sResourceManager"):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=False,
                config={"backend-type": "storage-class", "storage-class": "local-path"},
            ),
        )
    assert state.unit_status == ops.ActiveStatus("Standby (leader manages storage)")
