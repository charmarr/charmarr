# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for SonarrCharm reconciliation."""

from unittest.mock import patch

from ops.testing import Container, Exec, Mount, Relation, Secret, State

from charmarr_lib.core.interfaces import MediaStorageProviderData

from .conftest import SONARR_CONTAINER

CHOWN_EXEC = Exec(["chown", "-R", "1000:1000", "/config"])
TEST_API_KEY = "testkey123456789012345678901234"


def _make_storage_relation() -> Relation:
    """Create a media-storage relation with valid provider data."""
    data = MediaStorageProviderData(pvc_name="charmarr-shared")
    return Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": data.model_dump_json()},
    )


def test_reconcile_creates_api_key_secret(ctx, mock_k8s, tmp_path):
    """Reconcile creates API key secret and writes config.xml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.generate_api_key", return_value=TEST_API_KEY),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container], relations=[_make_storage_relation()]),
        )

    assert len(state.secrets) == 1
    secret = next(iter(state.secrets))
    assert secret.tracked_content["api-key"] == TEST_API_KEY

    config_file = config_dir / "config.xml"
    assert config_file.exists()
    assert TEST_API_KEY in config_file.read_text()


def test_reconcile_builds_pebble_layer(ctx, mock_k8s, tmp_path):
    """Reconcile builds correct Pebble layer with user-id/group-id."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container], relations=[_make_storage_relation()]),
        )

    container_out = state.get_container("sonarr")
    layer = container_out.layers.get("sonarr")
    assert layer is not None
    service = layer.services["sonarr"]
    assert service.user_id == 1000
    assert service.group_id == 1000
    assert "Sonarr" in service.command
    assert service.environment.get("HOME") == "/config"


def test_reconcile_calls_vpn_gateway_client(ctx, mock_k8s, tmp_path):
    """Reconcile calls reconcile_gateway_client when VPN related."""
    from charmarr_lib.vpn.interfaces import VPNGatewayProviderData

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

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
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client") as mock_gw_client,
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                relations=[_make_storage_relation(), vpn_relation],
            ),
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
            State(leader=False, containers=[SONARR_CONTAINER]),
        )

    container_out = state.get_container("sonarr")
    check_layer = container_out.layers.get("sonarr-check")
    assert check_layer is not None
    assert "sonarr-ready" in check_layer.checks


def test_reconcile_skips_write_when_config_matches(ctx, mock_k8s, tmp_path):
    """Reconcile skips writing config when all managed fields already match."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.xml"
    config_content = (
        f"<Config><ApiKey>{TEST_API_KEY}</ApiKey><UrlBase>/sonarr</UrlBase>"
        "<Port>8989</Port><BindAddress>*</BindAddress></Config>"
    )
    config_file.write_text(config_content)

    container = Container(
        name="sonarr",
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
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[api_key_secret],
                relations=[_make_storage_relation()],
            ),
        )

    assert config_file.read_text() == config_content


def test_secret_rotate_updates_config(ctx, mock_k8s, tmp_path):
    """Secret rotation updates API key in config.xml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.xml"
    config_file.write_text(f"<Config><ApiKey>{TEST_API_KEY}</ApiKey></Config>")

    container = Container(
        name="sonarr",
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


def test_reconcile_syncs_trash_profiles_when_workload_ready(ctx, mock_k8s, tmp_path):
    """Reconcile syncs Trash profiles via Recyclarr when workload is ready."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
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
        patch("charm.SonarrCharm._is_workload_ready", return_value=True),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.SonarrCharm._sync_trash_profiles") as mock_sync,
        patch("charm.SonarrCharm._reconcile_download_clients"),
        patch("charm.SonarrCharm._reconcile_root_folder"),
        patch("charm.SonarrCharm._get_quality_profiles", return_value=[]),
        patch("charm.SonarrCharm._get_root_folders", return_value=[]),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[api_key_secret],
                config={"trash-profiles": "web-1080p"},
                relations=[_make_storage_relation()],
            ),
        )
        mock_sync.assert_called_once()


def test_reconcile_calls_download_client_reconciler(ctx, mock_k8s, tmp_path):
    """Reconcile calls _reconcile_download_clients when workload ready."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
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
        patch("charm.SonarrCharm._is_workload_ready", return_value=True),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.SonarrCharm._sync_trash_profiles"),
        patch("charm.SonarrCharm._reconcile_download_clients") as mock_reconcile,
        patch("charm.SonarrCharm._reconcile_root_folder"),
        patch("charm.SonarrCharm._get_quality_profiles", return_value=[]),
        patch("charm.SonarrCharm._get_root_folders", return_value=[]),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[api_key_secret],
                relations=[_make_storage_relation()],
            ),
        )
        mock_reconcile.assert_called_once()


def test_reconcile_calls_root_folder_reconciler(ctx, mock_k8s, tmp_path):
    """Reconcile calls _reconcile_root_folder when workload ready."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
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
        patch("charm.SonarrCharm._is_workload_ready", return_value=True),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.SonarrCharm._sync_trash_profiles"),
        patch("charm.SonarrCharm._reconcile_download_clients"),
        patch("charm.SonarrCharm._reconcile_root_folder") as mock_reconcile,
        patch("charm.SonarrCharm._get_quality_profiles", return_value=[]),
        patch("charm.SonarrCharm._get_root_folders", return_value=[]),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[api_key_secret],
                relations=[_make_storage_relation()],
            ),
        )
        mock_reconcile.assert_called_once()


def test_reconcile_warns_when_scaled(ctx, mock_k8s, tmp_path, caplog):
    """Reconcile logs warning when scaled beyond 1 unit."""
    import logging

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        caplog.at_level(logging.WARNING),
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                relations=[_make_storage_relation()],
                planned_units=2,
            ),
        )
    assert "Scaling > 1 not supported" in caplog.text


def test_configure_ingress_submits_route(ctx, mock_k8s, tmp_path):
    """Configure ingress submits route config when relation exists."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    ingress_relation = Relation(
        endpoint="istio-ingress-route",
        interface="istio_ingress_route",
    )

    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": TEST_API_KEY},
        owner="app",
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[api_key_secret],
                relations=[_make_storage_relation(), ingress_relation],
            ),
        )
    assert state is not None


def test_reconcile_publishes_media_indexer_requirer(ctx, mock_k8s, tmp_path):
    """Reconcile publishes data to media-indexer relation."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": TEST_API_KEY},
        owner="app",
    )

    media_indexer_relation = Relation(
        endpoint="media-indexer",
        interface="media-indexer",
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[api_key_secret],
                relations=[_make_storage_relation(), media_indexer_relation],
            ),
        )
    # Verify relation data was published
    relation_out = next(r for r in state.relations if r.endpoint == "media-indexer")
    assert "config" in relation_out.local_app_data


def test_reconcile_publishes_download_client_requirer(ctx, mock_k8s, tmp_path):
    """Reconcile publishes data to download-client relation."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    container = Container(
        name="sonarr",
        can_connect=True,
        mounts={"config": Mount(location="/config", source=config_dir)},
        execs={CHOWN_EXEC},
    )

    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": TEST_API_KEY},
        owner="app",
    )

    download_client_relation = Relation(
        endpoint="download-client",
        interface="download-client",
    )

    with (
        patch("charm.SonarrCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[api_key_secret],
                relations=[_make_storage_relation(), download_client_relation],
            ),
        )
    relation_out = next(r for r in state.relations if r.endpoint == "download-client")
    assert "config" in relation_out.local_app_data
