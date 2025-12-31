# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for OverseerrCharm status collection."""

from unittest.mock import patch

import ops
from ops.testing import Container, State

from .conftest import OVERSEERR_CONTAINER


def test_status_waiting_for_pebble(ctx):
    """Report waiting when Pebble not connected."""
    container = Container(name="overseerr", can_connect=False)

    state = ctx.run(
        ctx.on.collect_unit_status(),
        State(
            leader=True,
            containers=[container],
        ),
    )

    assert state.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_status_waiting_for_workload(ctx):
    """Report waiting when service not running."""
    with patch("charm.ensure_pebble_user"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[OVERSEERR_CONTAINER],
            ),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for workload")


def test_status_non_leader_standby(ctx):
    """Non-leader reports standby status."""
    state = ctx.run(
        ctx.on.collect_unit_status(),
        State(
            leader=False,
            containers=[OVERSEERR_CONTAINER],
        ),
    )

    assert state.unit_status == ops.WaitingStatus("Standby (non-leader)")


def test_status_scaling_blocked(ctx):
    """Scaling beyond 1 reports blocked for non-leader."""
    with patch.object(ops.Application, "planned_units", return_value=2):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=False,
                containers=[OVERSEERR_CONTAINER],
            ),
        )

    assert state.unit_status == ops.BlockedStatus(
        "Scaling not supported - only leader runs workload"
    )


def test_status_active_when_ready(ctx):
    """Report active when workload is running and API key exists."""
    container = Container(
        name="overseerr",
        can_connect=True,
        service_statuses={"overseerr": ops.pebble.ServiceStatus.ACTIVE},
    )

    with (
        patch("charm.OverseerrCharm._get_api_key", return_value="test-api-key"),
        patch("charm.OverseerrCharm._is_service_running", return_value=True),
        patch("charm.OverseerrCharm._is_workload_ready", return_value=True),
        patch("charm.OverseerrCharm._get_api_client") as mock_api_client,
    ):
        mock_api_client.return_value.__enter__.return_value.is_initialized.return_value = True
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=True, containers=[container]),
        )

    assert state.unit_status == ops.ActiveStatus()
