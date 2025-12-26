# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for qBittorrent API client."""

from unittest.mock import MagicMock, patch

import pytest

from _qbittorrent import QBittorrentApi, QBittorrentApiError


@pytest.fixture
def api():
    """Create API client with mocked httpx."""
    with patch("_qbittorrent._api.httpx.Client") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        client = QBittorrentApi("http://localhost:8080")
        client._mock = mock_client
        yield client


def test_authenticate_success(api):
    """Successful auth stores session cookie."""
    api._mock.post.return_value = MagicMock(status_code=200, text="Ok.")
    api.authenticate("admin", "pass")
    api._mock.post.assert_called_once()


def test_authenticate_failure(api):
    """Failed auth raises error."""
    api._mock.post.return_value = MagicMock(status_code=403, text="Fails.")
    with pytest.raises(QBittorrentApiError):
        api.authenticate("admin", "wrong")


def test_create_category_ignores_conflict(api):
    """Category creation ignores 409 (already exists)."""
    api._mock.post.return_value = MagicMock(status_code=409)
    api.create_category("movies", "/downloads/movies")


def test_context_manager_closes(api):
    """Context manager closes client."""
    with api:
        pass
    api._mock.close.assert_called_once()
