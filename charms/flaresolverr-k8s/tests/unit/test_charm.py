# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for FlareSolverr charm."""

from unittest.mock import patch

import ops
from ops import testing

from charm import FlareSolverrCharm


def _base_state(container: testing.Container, **kwargs) -> testing.State:
    """Create base state with required relations for service mesh."""
    return testing.State(containers=[container], **kwargs)


def test_pebble_ready_configures_layer():
    """Test that Pebble ready event configures the layer."""
    ctx = testing.Context(FlareSolverrCharm)
    container = testing.Container("flaresolverr", can_connect=True)
    state = _base_state(container, leader=True)

    with patch.object(FlareSolverrCharm, "_is_workload_ready", return_value=False):
        state_out = ctx.run(ctx.on.pebble_ready(container), state)

    flaresolverr_container = state_out.get_container("flaresolverr")
    layer = flaresolverr_container.layers.get("flaresolverr")
    assert layer is not None
    assert "flaresolverr" in layer.services


def test_workload_ready_publishes_url():
    """Test that workload ready state publishes relation data."""
    ctx = testing.Context(FlareSolverrCharm)
    container = testing.Container("flaresolverr", can_connect=True)
    relation = testing.Relation(endpoint="flaresolverr", interface="flaresolverr")
    state = _base_state(container, leader=True, relations=[relation])

    with patch.object(FlareSolverrCharm, "_is_workload_ready", return_value=True):
        state_out = ctx.run(ctx.on.pebble_ready(container), state)

    relation_out = state_out.get_relations("flaresolverr")[0]
    assert "config" in relation_out.local_app_data


def test_status_waiting_when_pebble_not_connected():
    """Test waiting status when Pebble is not connected."""
    ctx = testing.Context(FlareSolverrCharm)
    container = testing.Container("flaresolverr", can_connect=False)
    state = _base_state(container, leader=True)

    state_out = ctx.run(ctx.on.collect_unit_status(), state)

    assert state_out.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_status_active_when_workload_ready():
    """Test active status when workload is ready."""
    ctx = testing.Context(FlareSolverrCharm)
    container = testing.Container("flaresolverr", can_connect=True)
    state = _base_state(container, leader=True)

    with patch.object(FlareSolverrCharm, "_is_workload_ready", return_value=True):
        state_out = ctx.run(ctx.on.collect_unit_status(), state)

    assert state_out.unit_status == ops.ActiveStatus()
