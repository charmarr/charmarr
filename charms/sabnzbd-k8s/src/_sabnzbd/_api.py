# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd API client."""

import httpx

from _sabnzbd._constants import API_BASE_PATH


class SABnzbdApiError(Exception):
    """Base exception for SABnzbd API errors."""


class SABnzbdApi:
    """SABnzbd API client.

    Uses API key authentication. Pass the api_key to constructor.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout)

    def _url(self, mode: str, **params: str) -> str:
        """Build API URL with mode and optional parameters."""
        base = f"{self._base_url}{API_BASE_PATH}?apikey={self._api_key}&mode={mode}&output=json"
        for key, value in params.items():
            base += f"&{key}={value}"
        return base

    def get_version(self) -> str:
        """Get SABnzbd version (health check)."""
        response = self._client.get(self._url("version"))
        response.raise_for_status()
        data = response.json()
        return data.get("version", "")

    def set_config(self, section: str, keyword: str, value: str) -> None:
        """Set a config value."""
        response = self._client.get(
            self._url("set_config", section=section, keyword=keyword, value=value)
        )
        response.raise_for_status()

    def set_config_category(self, name: str, directory: str) -> None:
        """Set a category with its relative directory path."""
        response = self._client.get(
            self._url("set_config", section="categories", keyword=name, dir=directory)
        )
        response.raise_for_status()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "SABnzbdApi":
        return self

    def __exit__(self, *args) -> None:
        self.close()
