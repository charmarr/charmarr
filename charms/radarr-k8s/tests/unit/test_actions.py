# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for RadarrCharm actions."""

from unittest.mock import patch

import ops
import pytest
from ops.testing import ActionFailed, Container, Mount, State

from .conftest import RADARR_CONTAINER

CONFIG_XML = """<?xml version="1.0" encoding="utf-8"?>
<Config>
  <ApiKey>testkey123456789012345678901234</ApiKey>
  <Port>7878</Port>
</Config>
"""


def test_rotate_api_key_action(ctx, mock_k8s, tmp_path):
    """Test rotate-api-key action generates new key and updates config."""
    config_file = tmp_path / "config.xml"
    config_file.write_text(CONFIG_XML)

    container = Container(
        name="radarr",
        can_connect=True,
        mounts={"config": Mount(location="/config/config.xml", source=config_file)},
    )

    secret = ops.testing.Secret(
        tracked_content={"api-key": "testkey123456789012345678901234"},
        label="api-key",
    )

    with (
        patch("charm.RadarrCharm._is_workload_ready", return_value=True),
        patch("charm.RadarrCharm._is_service_running", return_value=False),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.generate_api_key", return_value="newkey__123456789012345678901234"),
    ):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[container], secrets=[secret]),
        )

    updated_content = config_file.read_text()
    assert "newkey__123456789012345678901234" in updated_content


def test_rotate_api_key_action_not_leader(ctx, mock_k8s):
    """Test rotate-api-key action fails for non-leader."""
    with (
        patch("charm.reconcile_gateway_client"),
        pytest.raises(ActionFailed) as exc_info,
    ):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=False, containers=[RADARR_CONTAINER]),
        )

    assert "leader unit" in str(exc_info.value)


def test_sync_trash_profiles_action(ctx, mock_k8s, tmp_path):
    """Test sync-trash-profiles action calls _sync_trash_profiles."""
    config_file = tmp_path / "config.xml"
    config_file.write_text(CONFIG_XML)

    container = Container(
        name="radarr",
        can_connect=True,
        mounts={"config": Mount(location="/config/config.xml", source=config_file)},
    )

    with (
        patch("charm.RadarrCharm._is_workload_ready", return_value=True),
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.RadarrCharm._sync_trash_profiles") as mock_sync,
        patch(
            "charm.RadarrCharm._get_api_key_secret",
            return_value=("testkey123456789012345678901234", "secret:123"),
        ),
    ):
        ctx.run(
            ctx.on.action("sync-trash-profiles"),
            State(
                leader=True,
                containers=[container],
                config={"trash-profiles": "hd-bluray-web"},
            ),
        )
        mock_sync.assert_called_once_with("testkey123456789012345678901234")


def test_sync_trash_profiles_action_not_leader(ctx, mock_k8s):
    """Test sync-trash-profiles action fails for non-leader."""
    with (
        patch("charm.reconcile_gateway_client"),
        pytest.raises(ActionFailed) as exc_info,
    ):
        ctx.run(
            ctx.on.action("sync-trash-profiles"),
            State(leader=False, containers=[RADARR_CONTAINER]),
        )

    assert "leader unit" in str(exc_info.value)


def test_sync_trash_profiles_no_api_key(ctx, mock_k8s, tmp_path):
    """Test sync-trash-profiles action fails when no API key secret exists."""
    config_file = tmp_path / "config.xml"
    config_file.write_text(CONFIG_XML)

    container = Container(
        name="radarr",
        can_connect=True,
        mounts={"config": Mount(location="/config/config.xml", source=config_file)},
    )

    with (
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch("charm.RadarrCharm._get_api_key_secret", return_value=None),
        pytest.raises(ActionFailed) as exc_info,
    ):
        ctx.run(
            ctx.on.action("sync-trash-profiles"),
            State(leader=True, containers=[container]),
        )

    assert "No API key" in str(exc_info.value)


def test_sync_trash_profiles_no_config(ctx, mock_k8s, tmp_path):
    """Test sync-trash-profiles action fails when no profiles configured."""
    config_file = tmp_path / "config.xml"
    config_file.write_text(CONFIG_XML)

    container = Container(
        name="radarr",
        can_connect=True,
        mounts={"config": Mount(location="/config/config.xml", source=config_file)},
    )

    with (
        patch("charm.ensure_pebble_user"),
        patch("charm.reconcile_gateway_client"),
        patch(
            "charm.RadarrCharm._get_api_key_secret",
            return_value=("testkey123456789012345678901234", "secret:123"),
        ),
        pytest.raises(ActionFailed) as exc_info,
    ):
        ctx.run(
            ctx.on.action("sync-trash-profiles"),
            State(leader=True, containers=[container], config={"trash-profiles": ""}),
        )

    assert "No trash-profiles" in str(exc_info.value)


def test_rotate_api_key_pebble_not_connected(ctx, mock_k8s):
    """Test rotate-api-key action fails when pebble not connected."""
    container = Container(name="radarr", can_connect=False)

    with (
        patch("charm.reconcile_gateway_client"),
        pytest.raises(ActionFailed) as exc_info,
    ):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[container]),
        )

    assert "Pebble" in str(exc_info.value)
