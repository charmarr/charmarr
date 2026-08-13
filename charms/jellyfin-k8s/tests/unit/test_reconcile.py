# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for JellyfinCharm reconciliation."""

from pathlib import Path
from unittest.mock import patch

import ops
from ops.testing import Container, Exec, Mount, Relation, State

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


def test_reconcile_non_leader_adds_check_layer(ctx, mock_k8s):
    """Non-leader adds readiness check layer but doesn't reconcile."""
    state = ctx.run(
        ctx.on.pebble_ready(JELLYFIN_CONTAINER),
        State(
            leader=False,
            containers=[JELLYFIN_CONTAINER],
            relations=[_make_storage_relation()],
        ),
    )

    container = state.get_container("jellyfin")
    assert "jellyfin-check" in container.layers


def test_reconcile_waits_for_pebble(ctx, mock_k8s):
    """Reconcile exits early when Pebble not connected."""
    container = Container(name="jellyfin", can_connect=False)

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
        State(leader=True, containers=[JELLYFIN_CONTAINER]),
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
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    mock_storage.assert_called_once()
    call_kwargs = mock_storage.call_args.kwargs
    assert call_kwargs["container_name"] == "jellyfin"
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
                containers=[JELLYFIN_CONTAINER],
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
                containers=[JELLYFIN_CONTAINER],
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
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    container = state.get_container("jellyfin")
    assert "jellyfin" in container.layers
    layer = container.layers["jellyfin"]
    service = layer.services["jellyfin"]
    assert service.command == "/usr/bin/jellyfin --ffmpeg=/usr/lib/jellyfin-ffmpeg/ffmpeg"
    assert service.user_id == 1000
    assert service.group_id == 1000


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
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
                config={"timezone": "America/New_York"},
            ),
        )

    container = state.get_container("jellyfin")
    layer = container.layers["jellyfin"]
    env = layer.services["jellyfin"].environment
    assert env.get("TZ") == "America/New_York"


def test_reconcile_sets_port(ctx, mock_k8s):
    """Reconcile opens the web UI and topology ports."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation()],
            ),
        )

    opened = {p.port for p in state.opened_ports}
    assert 8096 in opened
    assert all(p.protocol == "tcp" for p in state.opened_ports)


def test_reconcile_enables_metrics(ctx, mock_k8s, tmp_path):
    """Reconcile flips EnableMetrics to true in system.xml."""
    system_xml = tmp_path / "system.xml"
    system_xml.write_text(
        "<ServerConfiguration><EnableMetrics>false</EnableMetrics></ServerConfiguration>"
    )
    container = Container(
        name="jellyfin",
        can_connect=True,
        execs={
            Exec(["chown", "-R", "1000:1000", "/config"]),
            Exec(["mkdir", "-p", "/config/data", "/config/cache", "/config/log"]),
        },
        mounts={"config": Mount(location="/config", source=tmp_path)},
    )

    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                relations=[_make_storage_relation()],
            ),
        )

    assert "<EnableMetrics>true</EnableMetrics>" in Path(system_xml).read_text()


def test_configure_ingress_submits_route_on_config_changed(ctx, mock_k8s):
    """Configure ingress submits route config when config_changed fires with an ingress relation."""
    ingress_relation = Relation(
        endpoint="istio-ingress-route",
        interface="istio_ingress_route",
    )

    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[JELLYFIN_CONTAINER],
                relations=[_make_storage_relation(), ingress_relation],
            ),
        )

    relation_out = next(r for r in state.relations if r.endpoint == "istio-ingress-route")
    assert "config" in relation_out.local_app_data
