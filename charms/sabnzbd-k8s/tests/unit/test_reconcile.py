# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for SABnzbdCharm reconciliation."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from ops.testing import Container, Exec, Mount, Relation, Secret, State

from charmarr_lib.core.interfaces import MediaStorageProviderData
from charmarr_lib.vpn.interfaces import VPNGatewayProviderData

from .conftest import SABNZBD_CONTAINER


def test_reconcile_creates_api_key_secret(ctx, mock_k8s):
    """Reconcile creates API key secret when not exists."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )

    with (
        patch("charm.SABnzbdCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[SABNZBD_CONTAINER],
                relations=[storage_relation],
                config={"unsafe-mode": True},
            ),
        )

    assert len(state.secrets) == 1
    secret = next(iter(state.secrets))
    assert "api-key" in secret.tracked_content


def test_reconcile_builds_pebble_layer(ctx, mock_k8s):
    """Reconcile builds correct Pebble layer with user-id/group-id."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared", puid=1000, pgid=1000)
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )

    with (
        patch("charm.SABnzbdCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[SABNZBD_CONTAINER],
                relations=[storage_relation],
                config={"unsafe-mode": True},
            ),
        )

    container_out = state.get_container("sabnzbd")
    layer = container_out.layers.get("sabnzbd")
    assert layer is not None
    service = layer.services["sabnzbd"]
    assert service.user_id == 1000
    assert service.group_id == 1000
    assert "/app/sabnzbd/SABnzbd.py" in service.command
    assert service.environment.get("HOME") == "/config"
    assert service.environment.get("TZ") == "Etc/UTC"


def test_reconcile_calls_storage_volume(ctx, mock_k8s):
    """Reconcile calls reconcile_storage_volume."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )

    with (
        patch("charm.SABnzbdCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_storage_volume") as mock_storage,
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[SABNZBD_CONTAINER],
                relations=[storage_relation],
                config={"unsafe-mode": True},
            ),
        )
        mock_storage.assert_called_once()
        call_kwargs = mock_storage.call_args.kwargs
        assert call_kwargs["pvc_name"] == "charmarr-shared"
        assert call_kwargs["container_name"] == "sabnzbd"


def test_reconcile_calls_vpn_gateway_client(ctx, mock_k8s):
    """Reconcile calls reconcile_gateway_client when VPN related."""
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
        external_ip="185.112.34.56",
        instance_name="gluetun",
    )
    vpn_relation = Relation(
        endpoint="vpn-gateway",
        interface="vpn-gateway",
        remote_app_data={"config": vpn_data.model_dump_json()},
    )

    with (
        patch("charm.SABnzbdCharm._is_workload_ready", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client") as mock_gw_client,
    ):
        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[SABNZBD_CONTAINER],
                relations=[storage_relation, vpn_relation],
            ),
        )
        mock_gw_client.assert_called_once()
        call_kwargs = mock_gw_client.call_args.kwargs
        assert call_kwargs["killswitch"] is True
        assert call_kwargs["data"].vpn_connected is True


def test_ensure_user_exists_adds_user_and_group(ctx, mock_k8s):
    """_ensure_user_exists adds user/group entries when missing."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared", puid=1234, pgid=5678)
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        etc_dir = Path(tmpdir) / "etc"
        etc_dir.mkdir()
        group_file = etc_dir / "group"
        passwd_file = etc_dir / "passwd"
        group_file.write_text("root:x:0:\n")
        passwd_file.write_text("root:x:0:0::/root:/bin/sh\n")

        container = Container(
            name="sabnzbd",
            can_connect=True,
            execs={Exec(["chown", "-R", "1234:5678", "/config"])},
            mounts={
                "etc-group": Mount(location="/etc/group", source=group_file),
                "etc-passwd": Mount(location="/etc/passwd", source=passwd_file),
            },
        )

        with patch("charm.SABnzbdCharm._is_workload_ready", return_value=False):
            ctx.run(
                ctx.on.config_changed(),
                State(
                    leader=True,
                    containers=[container],
                    relations=[storage_relation],
                    config={"unsafe-mode": True},
                ),
            )

        assert ":5678:" in group_file.read_text()
        assert ":1234:" in passwd_file.read_text()


def test_secret_rotate_generates_new_api_key(ctx, mock_k8s):
    """Secret rotation generates new API key and rewrites config."""
    storage_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    storage_relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": storage_data.model_dump_json()},
    )
    secret = Secret(
        tracked_content={"api-key": "old-api-key-12345678901234567890"},
        label="api-key",
        owner="app",
    )

    with (
        patch("charm.SABnzbdCharm._is_workload_ready", return_value=False),
        patch("charm.SABnzbdCharm._is_service_running", return_value=False),
        patch("charm.ensure_pebble_user"),
    ):
        state = ctx.run(
            ctx.on.secret_rotate(secret),
            State(
                leader=True,
                containers=[SABNZBD_CONTAINER],
                relations=[storage_relation],
                secrets=[secret],
            ),
        )

    rotated_secret = next(iter(state.secrets))
    assert rotated_secret.tracked_content["api-key"] != "old-api-key-12345678901234567890"
