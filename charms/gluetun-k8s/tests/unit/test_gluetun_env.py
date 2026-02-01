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


def test_override_env_merges_on_top(ctx, mock_k8s_privileged):
    """Custom overrides are merged into the gluetun environment."""
    import json

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
                "custom-overrides": json.dumps({"EXTRA_VAR": "extra_value"}),
            },
            secrets=[secret],
        ),
    )
    container_out = state.get_container("gluetun")
    layer = container_out.layers.get("gluetun")
    env = layer.services["gluetun"].environment
    assert env.get("EXTRA_VAR") == "extra_value"
    assert env.get("VPN_SERVICE_PROVIDER") == "nordvpn"


def test_override_env_overrides_base_values(ctx, mock_k8s_privileged):
    """Custom overrides take precedence over charm-built values."""
    import json

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
                "custom-overrides": json.dumps({"VPN_TYPE": "openvpn", "DOT": "on"}),
            },
            secrets=[secret],
        ),
    )
    container_out = state.get_container("gluetun")
    layer = container_out.layers.get("gluetun")
    env = layer.services["gluetun"].environment
    assert env.get("VPN_TYPE") == "openvpn"
    assert env.get("DOT") == "on"


def test_override_without_private_key(ctx, mock_k8s_privileged):
    """Override mode builds layer without wireguard keys when no secret is set."""
    import json

    container = Container(name="gluetun", can_connect=True)
    state = ctx.run(
        ctx.on.config_changed(),
        State(
            leader=True,
            containers=[container],
            config={
                "cluster-cidrs": "10.1.0.0/16",
                "vpn-provider": "expressvpn",
                "custom-overrides": json.dumps(
                    {"VPN_TYPE": "openvpn", "OPENVPN_USER": "u", "OPENVPN_PASSWORD": "p"}
                ),
            },
        ),
    )
    container_out = state.get_container("gluetun")
    layer = container_out.layers.get("gluetun")
    env = layer.services["gluetun"].environment
    assert env.get("VPN_TYPE") == "openvpn"
    assert env.get("VPN_SERVICE_PROVIDER") == "expressvpn"
    assert env.get("OPENVPN_USER") == "u"
    assert "WIREGUARD_PRIVATE_KEY" not in env
