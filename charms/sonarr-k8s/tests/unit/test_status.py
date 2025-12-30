# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for SonarrCharm status collection."""

from unittest.mock import patch

import ops
from ops.testing import Container, Relation, Secret, State

from charmarr_lib.core.interfaces import MediaStorageProviderData

from .conftest import SONARR_CONTAINER


def _make_storage_relation() -> Relation:
    """Create a media-storage relation with valid provider data."""
    data = MediaStorageProviderData(pvc_name="charmarr-shared")
    return Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": data.model_dump_json()},
    )


def test_status_waiting_for_pebble(ctx, mock_k8s):
    """Status is waiting when Pebble not connected (with storage)."""
    container = Container(name="sonarr", can_connect=False)

    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=True, containers=[container], relations=[_make_storage_relation()]),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_status_blocked_without_media_storage(ctx, mock_k8s):
    """Charm is blocked without media-storage relation."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, containers=[SONARR_CONTAINER]),
    )
    assert state.unit_status == ops.BlockedStatus("Waiting for media-storage relation")


def test_status_waiting_for_api_key(ctx, mock_k8s):
    """Status is waiting when API key not yet available."""
    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[SONARR_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for API key")


def test_status_waiting_for_workload(ctx, mock_k8s):
    """Status is waiting when workload not ready."""
    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": "testkey123456789012345678901234"},
        owner="app",
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[SONARR_CONTAINER],
                secrets=[api_key_secret],
                relations=[_make_storage_relation()],
            ),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for workload")


def test_status_active_when_ready(ctx, mock_k8s):
    """Status is active when workload is ready."""
    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": "testkey123456789012345678901234"},
        owner="app",
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=True),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[SONARR_CONTAINER],
                secrets=[api_key_secret],
                relations=[_make_storage_relation()],
            ),
        )

    assert state.unit_status == ops.ActiveStatus()


def test_status_non_leader_standby(ctx, mock_k8s):
    """Non-leader shows standby status."""
    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=False,
                containers=[SONARR_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    assert state.unit_status == ops.WaitingStatus("Standby (non-leader)")
