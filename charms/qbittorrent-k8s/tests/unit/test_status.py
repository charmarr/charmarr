# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for QBittorrentCharm status collection."""

from unittest.mock import patch

import ops
from ops.testing import Container, Relation, State

from charmarr_lib.core.interfaces import MediaStorageProviderData
from charmarr_lib.vpn.interfaces import VPNGatewayProviderData

from .conftest import QBITTORRENT_CONTAINER


def test_waiting_for_pebble(ctx, mock_k8s):
    """Charm waits for Pebble when container not connected (with storage)."""
    container = Container(name="qbittorrent", can_connect=False)
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )
    state = ctx.run(
        ctx.on.start(),
        State(
            leader=True,
            containers=[container],
            relations=[storage_relation],
            config={"unsafe-mode": True},
        ),
    )
    assert state.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_blocked_without_media_storage(ctx, mock_k8s):
    """Charm is blocked without media-storage relation."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, containers=[QBITTORRENT_CONTAINER]),
    )
    assert state.unit_status == ops.BlockedStatus("Waiting for media-storage relation")


def test_non_leader_standby_status(ctx, mock_k8s):
    """Non-leader unit shows standby status."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )
    state = ctx.run(
        ctx.on.start(),
        State(
            leader=False,
            containers=[QBITTORRENT_CONTAINER],
            relations=[storage_relation],
            config={"unsafe-mode": True},
        ),
    )
    assert state.unit_status == ops.WaitingStatus("Standby (non-leader)")


def test_non_leader_blocked_when_scaled_beyond_one(ctx):
    """Non-leader unit is blocked when scaled beyond 1."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=False,
            containers=[QBITTORRENT_CONTAINER],
            planned_units=2,
        ),
    )
    assert state.unit_status == ops.BlockedStatus(
        "Scaling not supported - only leader runs workload"
    )


def test_leader_continues_when_scaled_beyond_one(ctx, mock_k8s):
    """Leader continues running when scaled beyond 1 (logs warning)."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[QBITTORRENT_CONTAINER],
            planned_units=2,
        ),
    )
    # Leader continues with normal status (blocked on storage in this case)
    assert state.unit_status == ops.BlockedStatus("Waiting for media-storage relation")


def test_waiting_for_vpn_when_related_but_not_connected(ctx, mock_k8s):
    """Charm waits for VPN when related but not connected."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )
    vpn_data = VPNGatewayProviderData(
        gateway_dns_name="gluetun.vpn.svc.cluster.local",
        cluster_cidrs="10.1.0.0/16",
        cluster_dns_ip="10.152.183.10",
        vpn_connected=False,
        instance_name="gluetun",
    )
    vpn_relation = Relation(
        endpoint="vpn-gateway",
        interface="vpn-gateway",
        remote_app_data={"config": vpn_data.model_dump_json()},
    )

    with (
        patch("charm.QBittorrentCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[QBITTORRENT_CONTAINER],
                relations=[storage_relation, vpn_relation],
            ),
        )
    assert state.unit_status == ops.WaitingStatus("Waiting for VPN connection")


def test_blocked_without_vpn_gateway_by_default(ctx, mock_k8s):
    """Charm is blocked without vpn-gateway relation when unsafe-mode is false (default)."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[QBITTORRENT_CONTAINER],
            relations=[storage_relation],
        ),
    )
    assert state.unit_status == ops.BlockedStatus(
        "Waiting for vpn-gateway relation (or set unsafe-mode=true)"
    )


def test_not_blocked_when_unsafe_mode_enabled(ctx, mock_k8s):
    """Charm proceeds without vpn-gateway when unsafe-mode is true."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )

    with (
        patch("charm.QBittorrentCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[QBITTORRENT_CONTAINER],
                relations=[storage_relation],
                config={"unsafe-mode": True},
            ),
        )
    assert state.unit_status == ops.WaitingStatus("Waiting for workload")


def test_not_blocked_when_vpn_gateway_related(ctx, mock_k8s):
    """Charm proceeds when vpn-gateway is related (regardless of unsafe-mode)."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )
    vpn_data = VPNGatewayProviderData(
        gateway_dns_name="gluetun.vpn.svc.cluster.local",
        cluster_cidrs="10.1.0.0/16",
        cluster_dns_ip="10.152.183.10",
        vpn_connected=True,
        instance_name="gluetun",
    )
    vpn_relation = Relation(
        endpoint="vpn-gateway",
        interface="vpn-gateway",
        remote_app_data={"config": vpn_data.model_dump_json()},
    )

    with (
        patch("charm.QBittorrentCharm._is_workload_ready", return_value=True),
        patch("charm.QBittorrentCharm._configure_app"),
        patch("charm.QBittorrentCharm._sync_categories"),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[QBITTORRENT_CONTAINER],
                relations=[storage_relation, vpn_relation],
            ),
        )
    assert state.unit_status == ops.ActiveStatus()
