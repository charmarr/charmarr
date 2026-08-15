# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for JellyfinCharm status collection."""

from unittest.mock import patch

import ops
from ops.testing import Container, Relation, State

from charmarr_lib.core.interfaces import MediaStorageProviderData

from .conftest import JELLYFIN_CONTAINER


def _make_storage_relation() -> Relation:
    """Create a media-storage relation with valid provider data."""
    data = MediaStorageProviderData(pvc_name="charmarr-shared")
    return Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": data.model_dump_json()},
    )


def test_status_waiting_for_pebble(ctx, mock_k8s):
    """Status is waiting when Pebble not connected."""
    container = Container(name="jellyfin", can_connect=False)

    state = ctx.run(
        ctx.on.collect_unit_status(),
        State(
            leader=True,
            containers=[container],
            relations=[_make_storage_relation()],
        ),
    )

    assert state.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_status_blocked_without_media_storage(ctx, mock_k8s):
    """Charm is blocked without media-storage relation."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, containers=[JELLYFIN_CONTAINER]),
    )
    assert state.unit_status == ops.BlockedStatus("Waiting for media-storage relation")


def test_status_waiting_for_workload(ctx, mock_k8s):
    """Status is waiting when workload not running."""
    with patch("charm.JellyfinCharm._is_service_running", return_value=False):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for workload")


def test_status_active_when_setup_complete(ctx, mock_k8s):
    """Status is active when workload running and setup wizard completed."""
    with (
        patch("charm.JellyfinCharm._is_service_running", return_value=True),
        patch("charm.JellyfinCharm._is_setup_complete", return_value=True),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    assert state.unit_status == ops.ActiveStatus()


def test_status_waiting_setup_incomplete(ctx, mock_k8s):
    """Status waiting when workload running but setup wizard not completed."""
    with (
        patch("charm.JellyfinCharm._is_service_running", return_value=True),
        patch("charm.JellyfinCharm._is_setup_complete", return_value=False),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    assert state.unit_status == ops.WaitingStatus("Complete setup in web UI")


def test_status_non_leader_standby(ctx, mock_k8s):
    """Non-leader shows standby status."""
    state = ctx.run(
        ctx.on.collect_unit_status(),
        State(
            leader=False,
            containers=[JELLYFIN_CONTAINER],
            relations=[_make_storage_relation()],
        ),
    )

    assert state.unit_status == ops.WaitingStatus("Standby (non-leader)")
