# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for ProwlarrCharm reconciliation."""

from unittest.mock import patch

from ops.testing import Container, Exec, Mount, Secret, State

from .conftest import PROWLARR_CONTAINER

CHOWN_EXEC = Exec(["chown", "-R", "1000:1000", "/config"])
TEST_API_KEY = "testkey123456789012345678901234"


def test_reconcile_creates_api_key_secret(ctx, mock_k8s, tmp_path):
    """Reconcile creates API key secret and writes config.xml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="prowlarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    with (
        patch("charm.ProwlarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.generate_api_key", return_value="testkey123456789012345678901234"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container]),
        )

    assert len(state.secrets) == 1
    secret = next(iter(state.secrets))
    assert secret.tracked_content["api-key"] == "testkey123456789012345678901234"

    config_file = config_dir / "config.xml"
    assert config_file.exists()
    assert "testkey123456789012345678901234" in config_file.read_text()


def test_reconcile_builds_pebble_layer(ctx, mock_k8s, tmp_path):
    """Reconcile builds correct Pebble layer with user-id/group-id."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="prowlarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    with (
        patch("charm.ProwlarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container]),
        )

    container_out = state.get_container("prowlarr")
    layer = container_out.layers.get("prowlarr")
    assert layer is not None
    service = layer.services["prowlarr"]
    assert service.user_id == 1000
    assert service.group_id == 1000
    assert "Prowlarr" in service.command
    assert service.environment.get("HOME") == "/config"


def test_reconcile_calls_vpn_gateway_client(ctx, mock_k8s, tmp_path):
    """Reconcile calls reconcile_gateway_client when VPN related."""
    from charmarr_lib.vpn.interfaces import VPNGatewayProviderData

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="prowlarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    from ops.testing import Relation

    vpn_data = VPNGatewayProviderData(
        gateway_dns_name="gluetun.vpn.svc.cluster.local",
        cluster_cidrs="10.1.0.0/16",
        cluster_dns_ip="10.152.183.10",
        vpn_connected=True,
        external_ip="185.112.34.56",
        instance_name="gluetun",
    )
    vpn_relation = Relation(
        endpoint="vpn-gateway",
        interface="vpn-gateway",
        remote_app_data={"config": vpn_data.model_dump_json()},
    )

    with (
        patch("charm.ProwlarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client") as mock_gw_client,
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container], relations=[vpn_relation]),
        )
        mock_gw_client.assert_called_once()
        call_kwargs = mock_gw_client.call_args.kwargs
        assert call_kwargs["killswitch"] is False
        assert call_kwargs["data"].vpn_connected is True


def test_non_leader_only_registers_check(ctx, mock_k8s):
    """Non-leader units only register readiness check."""
    with patch("charm.reconcile_gateway_client"):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=False, containers=[PROWLARR_CONTAINER]),
        )

    container_out = state.get_container("prowlarr")
    check_layer = container_out.layers.get("prowlarr-check")
    assert check_layer is not None
    assert "prowlarr-ready" in check_layer.checks


def test_reconcile_skips_write_when_config_matches(ctx, mock_k8s, tmp_path):
    """Reconcile skips writing config when all managed fields already match."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.xml"
    initial_config = (
        f"<Config><ApiKey>{TEST_API_KEY}</ApiKey><UrlBase>/prowlarr</UrlBase>"
        "<Port>9696</Port><BindAddress>*</BindAddress></Config>"
    )
    config_file.write_text(initial_config)

    container = Container(
        name="prowlarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": TEST_API_KEY},
        owner="app",
    )

    with (
        patch("charm.ProwlarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container], secrets=[api_key_secret]),
        )

    assert config_file.read_text() == initial_config


def test_secret_rotate_updates_config(ctx, mock_k8s, tmp_path):
    """Secret rotation updates API key in config.xml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.xml"
    config_file.write_text(f"<Config><ApiKey>{TEST_API_KEY}</ApiKey></Config>")

    container = Container(
        name="prowlarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": TEST_API_KEY},
        owner="app",
    )

    new_key = "newkey99887766554433221100aabbcc"

    with (
        patch("charm.generate_api_key", return_value=new_key),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.secret_rotate(api_key_secret),
            State(leader=True, containers=[container], secrets=[api_key_secret]),
        )

    assert new_key in config_file.read_text()
    rotated_secret = next(iter(state.secrets))
    assert rotated_secret.tracked_content["api-key"] == new_key
