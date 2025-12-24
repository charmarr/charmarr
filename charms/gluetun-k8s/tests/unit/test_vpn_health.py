# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for VPN health monitoring and gateway functionality."""

from unittest.mock import patch

import ops
from ops.testing import Container, Secret, State

from charm import VPNHealthStatus

GLUETUN_CONTAINER = Container(name="gluetun", can_connect=True)


def test_vpn_status_shows_connected_with_ip(ctx):
    """Status shows VPN connected with external IP when healthy."""
    secret = Secret(tracked_content={"private-key": "test-key"})
    health = VPNHealthStatus(connected=True, external_ip="185.112.34.56")
    with (
        patch("charm.K8sResourceManager"),
        patch("charm.GluetunCharm._check_vpn_health", return_value=health),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[GLUETUN_CONTAINER],
                config={
                    "cluster-cidrs": "10.1.0.0/16",
                    "vpn-provider": "nordvpn",
                    "wireguard-private-key-secret": secret.id,
                },
                secrets=[secret],
            ),
        )
    assert state.unit_status == ops.ActiveStatus("VPN connected (185.112.34.56)")


def test_vpn_status_shows_not_connected(ctx):
    """Status shows VPN not connected when unhealthy."""
    secret = Secret(tracked_content={"private-key": "test-key"})
    health = VPNHealthStatus(connected=False, error="API unreachable")
    with (
        patch("charm.K8sResourceManager"),
        patch("charm.GluetunCharm._check_vpn_health", return_value=health),
    ):
        state = ctx.run(
            ctx.on.collect_unit_status(),
            State(
                leader=True,
                containers=[GLUETUN_CONTAINER],
                config={
                    "cluster-cidrs": "10.1.0.0/16",
                    "vpn-provider": "nordvpn",
                    "wireguard-private-key-secret": secret.id,
                },
                secrets=[secret],
            ),
        )
    assert state.unit_status == ops.WaitingStatus("VPN not connected")


def test_reconcile_calls_gateway_when_vpn_connected(ctx, mock_k8s_privileged):
    """Reconcile calls reconcile_gateway when VPN is connected."""
    from charm import GluetunCharm

    secret = Secret(tracked_content={"private-key": "test-key"})
    health = VPNHealthStatus(connected=True, external_ip="185.112.34.56")
    with (
        patch.object(GluetunCharm, "_check_vpn_health", return_value=health),
        patch("charm.reconcile_gateway") as mock_gateway,
    ):
        ctx.run(
            ctx.on.update_status(),
            State(
                leader=True,
                containers=[GLUETUN_CONTAINER],
                config={
                    "cluster-cidrs": "10.1.0.0/16,10.152.183.0/24",
                    "vpn-provider": "nordvpn",
                    "wireguard-private-key-secret": secret.id,
                },
                secrets=[secret],
            ),
        )
        mock_gateway.assert_called_once()
        call_kwargs = mock_gateway.call_args.kwargs
        assert call_kwargs["input_cidrs"] == []
        assert call_kwargs["data"].vpn_connected is True


def test_reconcile_calls_gateway_even_when_vpn_disconnected(ctx, mock_k8s_privileged):
    """Reconcile calls reconcile_gateway even when VPN is not connected."""
    from charm import GluetunCharm

    secret = Secret(tracked_content={"private-key": "test-key"})
    health = VPNHealthStatus(connected=False, error="API unreachable")
    with (
        patch.object(GluetunCharm, "_check_vpn_health", return_value=health),
        patch("charm.reconcile_gateway") as mock_gateway,
    ):
        ctx.run(
            ctx.on.update_status(),
            State(
                leader=True,
                containers=[GLUETUN_CONTAINER],
                config={
                    "cluster-cidrs": "10.1.0.0/16",
                    "vpn-provider": "nordvpn",
                    "wireguard-private-key-secret": secret.id,
                },
                secrets=[secret],
            ),
        )
        mock_gateway.assert_called_once()
        provider_data = mock_gateway.call_args.kwargs["data"]
        assert provider_data.vpn_connected is False
