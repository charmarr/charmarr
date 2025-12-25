# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for gluetun-k8s config validation."""

import ops
from ops.testing import Container, Secret, State

GLUETUN_CONTAINER = Container(name="gluetun", can_connect=True)


def test_blocked_without_cluster_cidrs(ctx):
    """cluster-cidrs is required."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(leader=True, containers=[GLUETUN_CONTAINER]),
    )
    assert state.unit_status == ops.BlockedStatus("cluster-cidrs config is required")


def test_blocked_without_vpn_provider(ctx):
    """vpn-provider is required."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[GLUETUN_CONTAINER],
            config={"cluster-cidrs": "10.1.0.0/16,10.152.183.0/24"},
        ),
    )
    assert state.unit_status == ops.BlockedStatus("vpn-provider config is required")


def test_blocked_openvpn_not_supported(ctx):
    """OpenVPN is not supported."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[GLUETUN_CONTAINER],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-type": "openvpn",
            },
        ),
    )
    assert state.unit_status == ops.BlockedStatus("OpenVPN is not supported")


def test_blocked_mullvad_requires_wireguard_addresses(ctx):
    """Mullvad provider requires wireguard-addresses."""
    secret = Secret(tracked_content={"private-key": "test-key"})
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[GLUETUN_CONTAINER],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-provider": "mullvad",
                "wireguard-private-key-secret": secret.id,
            },
            secrets=[secret],
        ),
    )
    assert state.unit_status == ops.BlockedStatus(
        "wireguard-addresses is required for provider 'mullvad'"
    )


def test_blocked_custom_requires_all_fields(ctx):
    """Custom provider requires endpoint IP and public key."""
    secret = Secret(tracked_content={"private-key": "test-key"})
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[GLUETUN_CONTAINER],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-provider": "custom",
                "wireguard-private-key-secret": secret.id,
                "wireguard-addresses": "10.64.222.21/32",
            },
            secrets=[secret],
        ),
    )
    assert state.unit_status == ops.BlockedStatus(
        "vpn-endpoint-ip is required for custom provider"
    )


def test_non_leader_standby_status(ctx, mock_k8s):
    """Non-leader unit shows standby status with valid config."""
    secret = Secret(tracked_content={"private-key": "test-key"})
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=False,
            containers=[GLUETUN_CONTAINER],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-provider": "nordvpn",
                "wireguard-private-key-secret": secret.id,
            },
            secrets=[secret],
        ),
    )
    assert state.unit_status == ops.WaitingStatus("Standby (non-leader unit)")


def test_blocked_when_secret_missing_private_key(ctx, mock_k8s):
    """Charm is blocked when secret exists but missing private-key attribute."""
    secret = Secret(tracked_content={"wrong-key": "value"})
    state = ctx.run(
        ctx.on.config_changed(),
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
    assert state.unit_status == ops.BlockedStatus("Secret not found or missing private-key")


def test_non_leader_blocked_when_scaled_beyond_one(ctx):
    """Non-leader unit is blocked when scaled beyond 1."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=False,
            containers=[GLUETUN_CONTAINER],
            planned_units=2,
        ),
    )
    assert state.unit_status == ops.BlockedStatus(
        "Scaling not supported - only leader runs workload"
    )


def test_leader_continues_when_scaled_beyond_one(ctx):
    """Leader continues running when scaled beyond 1 (logs warning)."""
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[GLUETUN_CONTAINER],
            planned_units=2,
        ),
    )
    # Leader continues with normal status (config validation in this case)
    assert state.unit_status == ops.BlockedStatus("cluster-cidrs config is required")
