# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for OverseerrCharm reconciliation."""

from unittest.mock import patch

import ops
from ops.testing import Container, State

from .conftest import OVERSEERR_CONTAINER


def test_reconcile_non_leader_adds_check_layer(ctx):
    """Non-leader adds readiness check layer but doesn't reconcile."""
    state = ctx.run(
        ctx.on.pebble_ready(OVERSEERR_CONTAINER),
        State(
            leader=False,
            containers=[OVERSEERR_CONTAINER],
        ),
    )

    container = state.get_container("overseerr")
    assert "overseerr-check" in container.layers


def test_reconcile_waits_for_pebble(ctx):
    """Reconcile exits early when Pebble not connected."""
    container = Container(name="overseerr", can_connect=False)

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[container],
        ),
    )

    assert state.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_reconcile_adds_pebble_layer(ctx):
    """Reconcile adds Pebble layer with correct service config."""
    with patch("charm.ensure_pebble_user"):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[OVERSEERR_CONTAINER],
            ),
        )

    container = state.get_container("overseerr")
    assert "overseerr" in container.layers
    layer = container.layers["overseerr"]
    assert "overseerr" in layer.services
    service = layer.services["overseerr"]
    assert service.command == "/usr/bin/node dist/index.js"
    assert service.user_id == 1000
    assert service.group_id == 1000


def test_reconcile_sets_log_level(ctx):
    """Pebble layer includes configured log level."""
    with patch("charm.ensure_pebble_user"):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[OVERSEERR_CONTAINER],
                config={"log-level": "debug"},
            ),
        )

    container = state.get_container("overseerr")
    layer = container.layers["overseerr"]
    env = layer.services["overseerr"].environment
    assert env.get("LOG_LEVEL") == "DEBUG"


def test_reconcile_sets_port(ctx):
    """Reconcile opens port 5055."""
    with patch("charm.ensure_pebble_user"):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[OVERSEERR_CONTAINER],
            ),
        )

    assert len(state.opened_ports) == 1
    port = next(iter(state.opened_ports))
    assert port.port == 5055
    assert port.protocol == "tcp"
