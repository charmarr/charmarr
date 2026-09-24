# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""qBittorrent WebUI API client."""

import json

import httpx

from _qbittorrent._constants import API_BASE_PATH


class QBittorrentApiError(Exception):
    """Base exception for qBittorrent API errors."""


class QBittorrentApi:
    """qBittorrent WebUI API client.

    Uses cookie-based session authentication. Call authenticate() before
    making other API calls.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def _url(self, path: str) -> str:
        """Build full API URL for given path."""
        return f"{self._base_url}{API_BASE_PATH}{path}"

    def authenticate(self, username: str, password: str) -> None:
        """Authenticate and store session cookie.

        A successful login answers 200 with "Ok." up to qBittorrent 5.1 and an
        empty 204 from 5.2, setting the session cookie either way. A rejected one
        is a 200 carrying "Fails." up to 5.1 and a 401 from 5.2.
        """
        response = self._client.post(
            self._url("/auth/login"),
            data={"username": username, "password": password},
        )
        if not response.is_success or response.text.strip() == "Fails.":
            detail = response.text.strip() or f"HTTP {response.status_code}"
            raise QBittorrentApiError(f"Authentication failed: {detail}")

    def get_version(self) -> str:
        """Get qBittorrent version (health check)."""
        response = self._client.get(self._url("/app/version"))
        response.raise_for_status()
        return response.text

    def set_preferences(self, prefs: dict) -> None:
        """Set application preferences."""
        response = self._client.post(
            self._url("/app/setPreferences"),
            data={"json": json.dumps(prefs)},
        )
        response.raise_for_status()

    def create_category(self, name: str, save_path: str) -> None:
        """Create a category with save path."""
        response = self._client.post(
            self._url("/torrents/createCategory"),
            data={"category": name, "savePath": save_path},
        )
        if response.status_code == 409:
            return
        response.raise_for_status()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "QBittorrentApi":
        return self

    def __exit__(self, *args) -> None:
        self.close()
