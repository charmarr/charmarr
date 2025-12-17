# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for native-nfs backend."""

from unittest.mock import patch

import ops
from ops.testing import State


def test_blocked_not_implemented(ctx):
    """Native-NFS backend shows blocked status (not yet implemented)."""
    with patch("charm.K8sResourceManager"):
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
    assert state.unit_status == ops.BlockedStatus("native-nfs backend not yet implemented")
