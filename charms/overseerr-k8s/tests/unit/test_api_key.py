# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for API key management."""

import json
from unittest.mock import MagicMock, patch

import ops
from ops.testing import Container, Exec, Secret, State

from .conftest import OVERSEERR_CONTAINER


def test_get_api_key_reads_settings(ctx):
    """API key is read from settings.json."""
    settings = {"main": {"apiKey": "test-key-123"}}
    container = Container(
        name="overseerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/config"])},
    )

    with (
        patch("charm.ensure_pebble_user"),
        patch.object(
            ops.Container, "pull", return_value=MagicMock(read=lambda: json.dumps(settings))
        ),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container]),
        )

    # Settings were read, secret created
    assert any(s.label == "api-key" for s in state.secrets)


def test_get_api_key_returns_none_on_missing_file(ctx):
    """Returns None when settings.json doesn't exist."""
    with patch("charm.ensure_pebble_user"):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[OVERSEERR_CONTAINER]),
        )

    # API key not found, reconcile exits early
    assert state.unit_status == ops.WaitingStatus("Waiting for API key")


def test_ensure_api_key_creates_secret(ctx):
    """API key secret is created when it doesn't exist."""
    settings = {"main": {"apiKey": "new-api-key"}}
    container = Container(
        name="overseerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/config"])},
    )

    with (
        patch("charm.ensure_pebble_user"),
        patch.object(
            ops.Container, "pull", return_value=MagicMock(read=lambda: json.dumps(settings))
        ),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container]),
        )

    # Secret was created
    assert any(s.label == "api-key" for s in state.secrets)


def test_ensure_api_key_updates_on_drift(ctx):
    """API key secret is updated when it drifts from settings.json."""
    settings = {"main": {"apiKey": "new-api-key"}}
    existing_secret = Secret(
        tracked_content={"api-key": "old-api-key"},
        label="api-key",
        owner="app",
    )
    container = Container(
        name="overseerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/config"])},
    )

    with (
        patch("charm.ensure_pebble_user"),
        patch.object(
            ops.Container, "pull", return_value=MagicMock(read=lambda: json.dumps(settings))
        ),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container], secrets=[existing_secret]),
        )

    # Secret content was updated
    secret = next(s for s in state.secrets if s.label == "api-key")
    assert secret.latest_content == {"api-key": "new-api-key"}


def test_get_api_key_returns_none_on_invalid_json(ctx):
    """Returns None when settings.json contains invalid JSON."""
    container = Container(
        name="overseerr",
        can_connect=True,
        execs={Exec(["chown", "-R", "1000:1000", "/config"])},
    )

    with (
        patch("charm.ensure_pebble_user"),
        patch.object(ops.Container, "pull", return_value=MagicMock(read=lambda: "not valid json")),
    ):
        state = ctx.run(
            ctx.on.config_changed(),
            State(leader=True, containers=[container]),
        )

    assert state.unit_status == ops.WaitingStatus("Waiting for API key")
