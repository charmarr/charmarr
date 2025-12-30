# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for PlexCharm reconciliation."""

from unittest.mock import patch

import ops
from ops.testing import Container, Relation, State

from charmarr_lib.core.interfaces import MediaStorageProviderData

from .conftest import PLEX_CONTAINER


def _make_storage_relation() -> Relation:
    """Create a media-storage relation with valid provider data."""
    data = MediaStorageProviderData(pvc_name="charmarr-shared")
    return Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": data.model_dump_json()},
    )


def test_reconcile_non_leader_adds_check_layer(ctx, mock_k8s):
    """Non-leader adds readiness check layer but doesn't reconcile."""
    state = ctx.run(
        ctx.on.pebble_ready(PLEX_CONTAINER),
        State(
            leader=False,
            containers=[PLEX_CONTAINER],
            relations=[_make_storage_relation()],
        ),
    )

    container = state.get_container("plex")
    assert "plex-check" in container.layers


def test_reconcile_waits_for_pebble(ctx, mock_k8s):
    """Reconcile exits early when Pebble not connected."""
    container = Container(name="plex", can_connect=False)

    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[container],
            relations=[_make_storage_relation()],
        ),
    )

    assert state.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_reconcile_waits_for_storage(ctx, mock_k8s):
    """Reconcile exits early when storage relation missing."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, containers=[PLEX_CONTAINER]),
    )

    assert state.unit_status == ops.BlockedStatus("Waiting for media-storage relation")


def test_reconcile_mounts_storage(ctx, mock_k8s):
    """Reconcile calls reconcile_storage_volume with correct args."""
    with (
        patch("charm.reconcile_storage_volume") as mock_storage,
        patch("charm.ensure_pebble_user"),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    mock_storage.assert_called_once()
    call_kwargs = mock_storage.call_args.kwargs
    assert call_kwargs["container_name"] == "plex"
    assert call_kwargs["pvc_name"] == "charmarr-shared"


def test_reconcile_hardware_transcoding_disabled(ctx, mock_k8s):
    """Hardware transcoding reconciler called with enabled=False by default."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.reconcile_hardware_transcoding") as mock_hw,
        patch("charm.ensure_pebble_user"),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    mock_hw.assert_called_once()
    assert mock_hw.call_args.kwargs["enabled"] is False


def test_reconcile_hardware_transcoding_enabled(ctx, mock_k8s):
    """Hardware transcoding reconciler called with enabled=True when configured."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.reconcile_hardware_transcoding") as mock_hw,
        patch("charm.ensure_pebble_user"),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
                config={"hardware-transcoding": True},
            ),
        )

    mock_hw.assert_called_once()
    assert mock_hw.call_args.kwargs["enabled"] is True


def test_reconcile_adds_pebble_layer(ctx, mock_k8s):
    """Reconcile adds Pebble layer with correct service config."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    container = state.get_container("plex")
    assert "plex" in container.layers
    layer = container.layers["plex"]
    assert "plex" in layer.services
    service = layer.services["plex"]
    assert service.command == '"/usr/lib/plexmediaserver/Plex Media Server"'
    assert service.user_id == 1000
    assert service.group_id == 1000


def test_reconcile_sets_claim_token_when_unclaimed(ctx, mock_k8s):
    """Pebble layer includes PLEX_CLAIM when server unclaimed and token configured."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
        patch("charm.PlexCharm._is_server_claimed", return_value=False),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
                config={"claim-token": "claim-testtoken123"},
            ),
        )

    container = state.get_container("plex")
    layer = container.layers["plex"]
    env = layer.services["plex"].environment
    assert env.get("PLEX_CLAIM") == "claim-testtoken123"


def test_reconcile_no_claim_token_when_claimed(ctx, mock_k8s):
    """Pebble layer excludes PLEX_CLAIM when server already claimed."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
        patch("charm.PlexCharm._is_server_claimed", return_value=True),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
                config={"claim-token": "claim-testtoken123"},
            ),
        )

    container = state.get_container("plex")
    layer = container.layers["plex"]
    env = layer.services["plex"].environment
    assert "PLEX_CLAIM" not in env


def test_reconcile_sets_timezone(ctx, mock_k8s):
    """Pebble layer includes configured timezone."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
                config={"timezone": "America/New_York"},
            ),
        )

    container = state.get_container("plex")
    layer = container.layers["plex"]
    env = layer.services["plex"].environment
    assert env.get("TZ") == "America/New_York"


def test_reconcile_sets_port(ctx, mock_k8s):
    """Reconcile opens port 32400."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[PLEX_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    assert len(state.opened_ports) == 1
    port = next(iter(state.opened_ports))
    assert port.port == 32400
    assert port.protocol == "tcp"
