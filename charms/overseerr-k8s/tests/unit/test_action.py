# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for charm actions."""

import json
from unittest.mock import patch

import ops
import pytest
from ops._private.harness import ActionFailed
from ops.testing import Container, Exec, Secret, State


def test_rotate_api_key_fails_non_leader(ctx):
    """Action fails on non-leader unit."""
    container = Container(name="overseerr", can_connect=True)

    with pytest.raises(ActionFailed, match="leader"):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=False, containers=[container]),
        )


def test_rotate_api_key_fails_no_pebble(ctx):
    """Action fails when Pebble not connected."""
    container = Container(name="overseerr", can_connect=False)

    with pytest.raises(ActionFailed, match="Pebble"):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[container]),
        )


def test_rotate_api_key_fails_no_api_key(ctx):
    """Action fails when API key not yet available."""
    container = Container(
        name="overseerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/config"])},
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
        label="overseerr-api-key",
        owner="app",
    )
    container = Container(
        name="overseerr",
        can_connect=True,
        mounts={
            "config": ops.testing.Mount(location="/config/settings.json", source=settings_file)
        },
        service_statuses={"overseerr": ops.pebble.ServiceStatus.ACTIVE},
    )

    with (
        patch("charm.OverseerrCharm._get_api_key", return_value="old-key"),
        patch("charm.OverseerrCharm._is_service_running", return_value=False),
        patch("charm.generate_api_key", return_value="new-rotated-key"),
    ):
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[container], secrets=[existing_secret]),
        )

    assert "new-rotated-key" in settings_file.read_text()
