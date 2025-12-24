# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for gluetun environment variable configuration."""

from ops.testing import Container, Secret, State


def test_env_includes_provider_and_private_key(ctx, mock_k8s_privileged):
    """Environment includes provider and WireGuard private key."""
    secret = Secret(tracked_content={"private-key": "test-private-key-value"})
    container = Container(name="gluetun", can_connect=True)
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[container],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-provider": "nordvpn",
                "wireguard-private-key-secret": secret.id,
            },
            secrets=[secret],
        ),
    )
    container_out = state.get_container("gluetun")
    layer = container_out.layers.get("gluetun")
    env = layer.services["gluetun"].environment
    assert env.get("VPN_SERVICE_PROVIDER") == "nordvpn"
    assert env.get("WIREGUARD_PRIVATE_KEY") == "test-private-key-value"


def test_env_includes_optional_server_countries(ctx, mock_k8s_privileged):
    """Environment includes optional server-countries when configured."""
    secret = Secret(tracked_content={"private-key": "key"})
    container = Container(name="gluetun", can_connect=True)
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[container],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-provider": "nordvpn",
                "wireguard-private-key-secret": secret.id,
                "server-countries": "Netherlands,Germany",
            },
            secrets=[secret],
        ),
    )
    container_out = state.get_container("gluetun")
    layer = container_out.layers.get("gluetun")
    assert layer.services["gluetun"].environment.get("SERVER_COUNTRIES") == "Netherlands,Germany"


def test_env_for_custom_provider(ctx, mock_k8s_privileged):
    """Custom provider environment includes VPN endpoint configuration."""
    secret = Secret(tracked_content={"private-key": "key"})
    container = Container(name="gluetun", can_connect=True)
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[container],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-provider": "custom",
                "wireguard-private-key-secret": secret.id,
                "wireguard-addresses": "10.64.222.21/32",
                "vpn-endpoint-ip": "1.2.3.4",
                "vpn-endpoint-port": 51820,
                "wireguard-public-key": "server-pubkey",
            },
            secrets=[secret],
        ),
    )
    container_out = state.get_container("gluetun")
    layer = container_out.layers.get("gluetun")
    env = layer.services["gluetun"].environment
    assert env.get("VPN_SERVICE_PROVIDER") == "custom"
    assert env.get("VPN_ENDPOINT_IP") == "1.2.3.4"
    assert env.get("WIREGUARD_PUBLIC_KEY") == "server-pubkey"
