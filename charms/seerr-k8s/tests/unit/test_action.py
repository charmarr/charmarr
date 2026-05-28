# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for charm actions."""

import json
from unittest.mock import patch

import ops
import pytest
from ops._private.harness import ActionFailed
from ops.testing import Container, Exec, Mount, Secret, State


def test_rotate_api_key_fails_non_leader(ctx):
    """Action fails on non-leader unit."""
    container = Container(name="seerr", can_connect=True)

    with pytest.raises(ActionFailed, match="leader"):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=False, containers=[container]),
        )


def test_rotate_api_key_fails_no_pebble(ctx):
    """Action fails when Pebble not connected."""
    container = Container(name="seerr", can_connect=False)

    with pytest.raises(ActionFailed, match="Pebble"):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[container]),
        )


def test_rotate_api_key_fails_no_api_key(ctx):
    """Action fails when API key not yet available."""
    container = Container(
        name="seerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/app/config"])},
    )

    with pytest.raises(ActionFailed, match="API key not available"):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[container]),
        )


def test_rotate_api_key_success(ctx, tmp_path):
    """Action rotates API key and restarts service."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"main": {"apiKey": "old-key"}}))

    existing_secret = Secret(
        tracked_content={"api-key": "old-key"},
        label="seerr-api-key",
        owner="app",
    )
    container = Container(
        name="seerr",
        can_connect=True,
        mounts={
            "config": ops.testing.Mount(location="/app/config/settings.json", source=settings_file)
        },
        service_statuses={"seerr": ops.pebble.ServiceStatus.ACTIVE},
    )

    with (
        patch("charm.SeerrCharm._get_api_key", return_value="old-key"),
        patch("charm.SeerrCharm._is_service_running", return_value=False),
        patch("charm.generate_api_key", return_value="new-rotated-key"),
    ):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[container], secrets=[existing_secret]),
        )

    assert "new-rotated-key" in settings_file.read_text()


def test_secret_rotate_updates_settings(ctx, tmp_path):
    """Secret rotation generates new API key and updates settings.json."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"main": {"apiKey": "old-api-key"}}))

    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": "old-api-key"},
        owner="app",
    )

    container = Container(
        name="seerr",
        can_connect=True,
        mounts={"config": Mount(location="/app/config/settings.json", source=settings_file)},
        execs={Exec(["chown", "-R", "1000:1000", "/app/config"])},
    )

    new_key = "new-rotated-api-key-123"

    with patch("charm.generate_api_key", return_value=new_key):
        state = ctx.run(
            ctx.on.secret_rotate(api_key_secret),
            State(leader=True, containers=[container], secrets=[api_key_secret]),
        )

    assert new_key in settings_file.read_text()
    rotated_secret = next(s for s in state.secrets if s.label == "api-key")
    assert rotated_secret.latest_content["api-key"] == new_key


def test_secret_rotate_non_leader_does_nothing(ctx):
    """Secret rotation is ignored on non-leader units."""
    api_key_secret = Secret(
        label="api-key",
        tracked_content={"api-key": "old-api-key"},
        owner="app",
    )

    container = Container(
        name="seerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/app/config"])},
    )

    with patch("charm.generate_api_key") as mock_generate:
        ctx.run(
            ctx.on.secret_rotate(api_key_secret),
            State(leader=False, containers=[container], secrets=[api_key_secret]),
        )

    mock_generate.assert_not_called()


def test_secret_rotate_wrong_label_does_nothing(ctx):
    """Secret rotation is ignored for secrets with non-API-key labels."""
    other_secret = Secret(
        label="some-other-secret",
        tracked_content={"value": "something"},
        owner="app",
    )

    container = Container(
        name="seerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/app/config"])},
    )

    with patch("charm.generate_api_key") as mock_generate:
        ctx.run(
            ctx.on.secret_rotate(other_secret),
            State(leader=True, containers=[container], secrets=[other_secret]),
        )

    mock_generate.assert_not_called()


def test_import_config_fails_non_leader(ctx):
    """Action fails on non-leader unit."""
    container = Container(name="seerr", can_connect=True)

    with pytest.raises(ActionFailed, match="leader"):
        ctx.run(
            ctx.on.action("import-config", params={"path": "/app/config/import.tgz"}),
            State(leader=False, containers=[container]),
        )


def test_import_config_fails_no_pebble(ctx):
    """Action fails when Pebble not connected."""
    container = Container(name="seerr", can_connect=False)

    with pytest.raises(ActionFailed, match="Pebble"):
        ctx.run(
            ctx.on.action("import-config", params={"path": "/app/config/import.tgz"}),
            State(leader=True, containers=[container]),
        )


def test_import_config_fails_missing_tarball(ctx):
    """Action fails when the tarball doesn't exist."""
    container = Container(name="seerr", can_connect=True)

    with pytest.raises(ActionFailed, match="Tarball not found"):
        ctx.run(
            ctx.on.action("import-config", params={"path": "/app/config/missing.tgz"}),
            State(leader=True, containers=[container]),
        )


def test_import_config_success(ctx, tmp_path):
    """Action wipes /app/config, extracts the tarball, and replans."""
    tarball = tmp_path / "import.tgz"
    tarball.write_bytes(b"fake tarball content")
    leftover = tmp_path / "settings.json"
    leftover.write_text("{}")

    container = Container(
        name="seerr",
        can_connect=True,
        mounts={
            "config": Mount(location="/app/config", source=tmp_path),
        },
        execs={
            Exec(["mv", "/app/config/import.tgz", "/tmp/seerr-import.tgz"], return_code=0),
            Exec(["sh", "-c"], return_code=0),
            Exec(["tar", "-xzf", "/tmp/seerr-import.tgz", "-C", "/app/config"], return_code=0),
            Exec(["rm", "-f", "/tmp/seerr-import.tgz"], return_code=0),
            Exec(["chown", "-R", "1000:1000", "/app/config"], return_code=0),
        },
    )

    with patch("charm.SeerrCharm._is_service_running", return_value=False):
        ctx.run(
            ctx.on.action("import-config", params={"path": "/app/config/import.tgz"}),
            State(leader=True, containers=[container]),
        )

    results = ctx.action_results
    assert results is not None
    assert "imported" in results["result"].lower()


def test_import_config_sha256_mismatch(ctx, tmp_path):
    """Action fails when provided sha256 doesn't match."""
    tarball = tmp_path / "import.tgz"
    tarball.write_bytes(b"fake tarball content")

    container = Container(
        name="seerr",
        can_connect=True,
        mounts={
            "config": Mount(location="/app/config", source=tmp_path),
        },
        execs={
            Exec(
                ["sha256sum", "/app/config/import.tgz"],
                stdout="actualsha  /app/config/import.tgz\n",
                return_code=0,
            ),
        },
    )

    with pytest.raises(ActionFailed, match="sha256 mismatch"):
        ctx.run(
            ctx.on.action(
                "import-config",
                params={"path": "/app/config/import.tgz", "sha256": "wrongsha"},
            ),
            State(leader=True, containers=[container]),
        )
