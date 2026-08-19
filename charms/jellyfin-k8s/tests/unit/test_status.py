# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for JellyfinCharm status collection."""

from unittest.mock import patch

import ops
from ops.testing import Container, Relation, Secret, State

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


def test_status_active_when_bootstrapped(ctx, mock_k8s):
    """Status is active once the charm holds an API key."""
    with patch("charm.JellyfinCharm._is_service_running", return_value=True):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
                secrets=[Secret({"api-key": "key"}, label="api-key", owner="app")],
            ),
        )

    assert state.unit_status == ops.ActiveStatus()


def test_status_waiting_while_bootstrapping(ctx, mock_k8s):
    """Status waits while the workload runs but bootstrap has not finished."""
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

    assert state.unit_status == ops.WaitingStatus("Bootstrapping Jellyfin")


def test_status_blocked_when_set_up_externally(ctx, mock_k8s):
    """Status is blocked when the wizard was completed outside the charm."""
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

    assert state.unit_status == ops.BlockedStatus("Jellyfin was set up outside the charm")


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
