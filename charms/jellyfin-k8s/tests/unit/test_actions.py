# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for JellyfinCharm actions."""

from unittest.mock import patch

import pytest
from ops.testing import ActionFailed, Secret, State

from .conftest import JELLYFIN_CONTAINER


def test_rotate_api_key_action(ctx, mock_k8s):
    """Test rotate-api-key action mints a replacement and stores it."""
    api_key_secret = Secret(label="api-key", tracked_content={"api-key": "old-key"}, owner="app")

    with patch("charm.JellyfinApi") as mock_class:
        api = mock_class.return_value.__enter__.return_value
        api.rotate_api_key.return_value = "new-key"

        state = ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=True, containers=[JELLYFIN_CONTAINER], secrets=[api_key_secret]),
        )

    assert ctx.action_results == {"result": "API key rotated"}
    rotated = next(s for s in state.secrets if s.label == "api-key")
    assert rotated.latest_content["api-key"] == "new-key"


def test_rotate_api_key_action_not_leader(ctx, mock_k8s):
    """Test rotate-api-key action fails for non-leader."""
    with pytest.raises(ActionFailed) as exc_info:
        ctx.run(
            ctx.on.action("rotate-api-key"),
            State(leader=False, containers=[JELLYFIN_CONTAINER]),
        )

    assert "leader unit" in str(exc_info.value)
