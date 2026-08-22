# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for headless first-run setup against a related media server."""

import json
from unittest.mock import patch

import ops
import pytest
from ops.testing import Container, Exec, Mount, Relation, Secret, State

from charmarr_lib.core import MediaServer
from charmarr_lib.core.interfaces import MediaServerProviderData


@pytest.fixture
def container(tmp_path):
    """Seerr container with a writable config directory."""
    (tmp_path / "settings.json").write_text(json.dumps({"main": {"apiKey": "seerr-key"}}))
    return Container(
        name="seerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/app/config"])},
        mounts={"config": Mount(location="/app/config", source=tmp_path)},
    )


def _write_media_server_type(tmp_path, server_type: int) -> None:
    settings = {"main": {"apiKey": "seerr-key", "mediaServerType": server_type}}
    (tmp_path / "settings.json").write_text(json.dumps(settings))


def _media_server_relation(server: MediaServer, credentials_secret_id: str | None) -> Relation:
    data = MediaServerProviderData(
        name=server.value,
        api_url=f"http://{server.value}:8096",
        server=server,
        credentials_secret_id=credentials_secret_id,
    )
    return Relation(
        endpoint="media-server",
        interface="media-server",
        remote_app_data={"config": data.model_dump_json()},
    )


def test_bootstrap_sets_up_jellyfin(ctx, container):
    """Jellyfin credentials drive setup, library sync, and initialize."""
    credentials = Secret(tracked_content={"username": "charmarr", "password": "pw"})

    with patch("charm.SeerrApi") as mock_class:
        api = mock_class.return_value.__enter__.return_value
        api.is_initialized.return_value = False
        api.sync_jellyfin_libraries.return_value = [{"id": "lib1"}, {"id": "lib2"}]

        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[credentials],
                relations=[_media_server_relation(MediaServer.JELLYFIN, credentials.id)],
            ),
        )

    api.jellyfin_setup.assert_called_once_with(
        hostname="jellyfin",
        port=8096,
        username="charmarr",
        password="pw",
        use_ssl=False,
    )
    api.enable_jellyfin_libraries.assert_called_once_with(["lib1", "lib2"])
    api.initialize.assert_called_once()


def test_bootstrap_skipped_once_set_up(ctx, container, tmp_path):
    """Setup runs once; a Jellyfin-backed install is left alone."""
    _write_media_server_type(tmp_path, 2)
    credentials = Secret(tracked_content={"username": "charmarr", "password": "pw"})

    with patch("charm.SeerrApi") as mock_class:
        api = mock_class.return_value.__enter__.return_value
        api.is_initialized.return_value = True

        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[credentials],
                relations=[_media_server_relation(MediaServer.JELLYFIN, credentials.id)],
            ),
        )

    api.jellyfin_setup.assert_not_called()


def test_bootstrap_resumes_after_partial_setup(ctx, container, tmp_path):
    """An install that authenticated but never initialized finishes the sequence."""
    _write_media_server_type(tmp_path, 2)
    credentials = Secret(tracked_content={"username": "charmarr", "password": "pw"})

    with patch("charm.SeerrApi") as mock_class:
        api = mock_class.return_value.__enter__.return_value
        api.is_initialized.return_value = False
        api.sync_jellyfin_libraries.return_value = []

        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                secrets=[credentials],
                relations=[_media_server_relation(MediaServer.JELLYFIN, credentials.id)],
            ),
        )

    api.jellyfin_setup.assert_not_called()
    api.enable_jellyfin_libraries.assert_not_called()
    api.initialize.assert_called_once()


def test_bootstrap_waits_for_credentials(ctx, container):
    """A Jellyfin provider that has not published credentials yet is not an error."""
    with patch("charm.SeerrApi") as mock_class:
        api = mock_class.return_value.__enter__.return_value
        api.is_initialized.return_value = False

        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                relations=[_media_server_relation(MediaServer.JELLYFIN, None)],
            ),
        )

    api.jellyfin_setup.assert_not_called()
    assert not isinstance(state.unit_status, ops.BlockedStatus)


def test_bootstrap_skipped_for_plex(ctx, container):
    """Plex keeps its operator-driven wizard."""
    with patch("charm.SeerrApi") as mock_class:
        api = mock_class.return_value.__enter__.return_value

        ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                relations=[_media_server_relation(MediaServer.PLEX, None)],
            ),
        )

    api.jellyfin_setup.assert_not_called()


@pytest.mark.parametrize(
    ("related", "configured"),
    [(MediaServer.JELLYFIN, 1), (MediaServer.PLEX, 2)],
)
def test_media_server_switch_blocks(ctx, container, tmp_path, related, configured):
    """Re-pointing Seerr at a different media server blocks rather than corrupts."""
    _write_media_server_type(tmp_path, configured)

    with patch("charm.SeerrApi") as mock_class:
        api = mock_class.return_value.__enter__.return_value

        state = ctx.run(
            ctx.on.config_changed(),
            State(
                leader=True,
                containers=[container],
                relations=[_media_server_relation(related, None)],
            ),
        )

    api.jellyfin_setup.assert_not_called()
    assert state.unit_status == ops.BlockedStatus(
        "Cannot switch media server after setup, check logs"
    )
