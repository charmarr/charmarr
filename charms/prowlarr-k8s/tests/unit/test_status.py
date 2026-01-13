# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for ProwlarrCharm status collection."""

from unittest.mock import patch

import ops
from ops.testing import Container, Secret, State

from .conftest import PROWLARR_CONTAINER


def test_status_waiting_for_pebble(ctx, mock_k8s):
    """Status is waiting when Pebble not connected."""
    container = Container(name="prowlarr", can_connect=False)

    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=True, containers=[container]),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_status_waiting_for_api_key(ctx, mock_k8s):
    """Status is waiting when API key not yet available."""
    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=True, containers=[PROWLARR_CONTAINER]),
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
        patch("charm.ProwlarrCharm._is_workload_ready", return_value=False),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=True, containers=[PROWLARR_CONTAINER], secrets=[api_key_secret]),
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
        patch("charm.ProwlarrCharm._is_workload_ready", return_value=True),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=True, containers=[PROWLARR_CONTAINER], secrets=[api_key_secret]),
        )

    assert state.unit_status == ops.ActiveStatus()


def test_status_non_leader_standby(ctx, mock_k8s):
    """Non-leader shows standby status."""
    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=False, containers=[PROWLARR_CONTAINER]),
        )

    assert state.unit_status == ops.WaitingStatus("Standby (non-leader)")


def test_status_scaling_blocked(ctx, mock_k8s):
    """Non-leader blocked when scaled beyond 1."""
    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(leader=False, containers=[PROWLARR_CONTAINER], planned_units=2),
        )

    assert state.unit_status == ops.BlockedStatus(
        "Scaling not supported - only leader runs workload"
    )


def test_status_vpn_waiting(ctx, mock_k8s):
    """Status waiting when VPN not connected."""
    from ops.testing import Relation

    from charmarr_lib.vpn.interfaces import VPNGatewayProviderData

    vpn_data = VPNGatewayProviderData(
        gateway_dns_name="gluetun.vpn.svc.cluster.local",
        cluster_cidrs="10.1.0.0/16",
        cluster_dns_ip="10.152.183.10",
        vpn_connected=False,
        external_ip=None,
        instance_name="gluetun",
    )
    vpn_relation = Relation(
        endpoint="vpn-gateway",
        interface="vpn-gateway",
        remote_app_data={"config": vpn_data.model_dump_json()},
    )
    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": "testkey123456789012345678901234"},
        owner="app",
    )

    with (
        patch("charm.ProwlarrCharm._is_workload_ready", return_value=True),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[PROWLARR_CONTAINER],
                secrets=[api_key_secret],
                relations=[vpn_relation],
            ),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for VPN connection")
