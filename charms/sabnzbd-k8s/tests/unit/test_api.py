# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for SABnzbd API client."""

from unittest.mock import MagicMock, patch

import pytest

from _sabnzbd import SABnzbdApi


@pytest.fixture
def api():
    """Create API client with mocked httpx."""
    with patch("_sabnzbd._api.httpx.Client") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        client = SABnzbdApi("http://localhost:8080", "test-api-key")
        client._mock = mock_client
        yield client


def test_get_version_success(api):
    """get_version returns version from API."""
    api._mock.get.return_value = MagicMock(status_code=200, json=lambda: {"version": "4.4.1"})
    version = api.get_version()
    assert version == "4.4.1"
    api._mock.get.assert_called_once()


def test_set_config_calls_api(api):
    """set_config calls API with correct parameters."""
    api._mock.get.return_value = MagicMock(status_code=200)
    api.set_config("misc", "complete_dir", "/data/usenet/complete")
    api._mock.get.assert_called_once()
    call_url = api._mock.get.call_args[0][0]
    assert "mode=set_config" in call_url
    assert "section=misc" in call_url
    assert "keyword=complete_dir" in call_url


def test_set_config_category_calls_api(api):
    """set_config_category calls API with correct parameters."""
    api._mock.get.return_value = MagicMock(status_code=200)
    api.set_config_category("radarr", "movies")
    api._mock.get.assert_called_once()
    call_url = api._mock.get.call_args[0][0]
    assert "mode=set_config" in call_url
    assert "section=categories" in call_url


def test_context_manager_closes(api):
    """Context manager closes client."""
    with api:
        pass
    api._mock.close.assert_called_once()
