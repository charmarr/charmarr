# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Overseerr API client."""

from typing import Any

import httpx


class OverseerrApiError(Exception):
    """Base exception for Overseerr API errors."""


class OverseerrApi:
    """Overseerr API client.

    Uses X-Api-Key header authentication.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(
            timeout=timeout,
            headers={"X-Api-Key": api_key},
        )

    def _url(self, path: str) -> str:
        """Build full API URL for given path."""
        return f"{self._base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
    ) -> Any:
        """Make API request."""
        url = self._url(path)
        try:
            if method == "GET":
                response = self._client.get(url)
            elif method == "POST":
                response = self._client.post(url, json=json_data)
            elif method == "PUT":
                response = self._client.put(url, json=json_data)
            elif method == "DELETE":
                response = self._client.delete(url)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json() if response.content else {}
        except httpx.HTTPStatusError as e:
            raise OverseerrApiError(f"API request failed: {e}") from e
        except httpx.RequestError as e:
            raise OverseerrApiError(f"Request failed: {e}") from e

    def get_status(self) -> dict:
        """Get Overseerr status (health check)."""
        return self._request("GET", "/api/v1/status")

    def is_initialized(self) -> bool:
        """Check if Overseerr has completed initial setup.

        Overseerr returns 403 on user-authenticated endpoints until
        initial setup (Plex OAuth) creates the admin user. The /auth/me
        endpoint requires user auth and is not integration-specific.
        """
        try:
            self._request("GET", "/api/v1/auth/me")
            return True
        except OverseerrApiError:
            return False

    def get_radarr_servers(self) -> list[dict]:
        """Get configured Radarr servers."""
        result = self._request("GET", "/api/v1/settings/radarr")
        return result if isinstance(result, list) else []

    def add_radarr_server(self, config: dict) -> dict:
        """Add a new Radarr server."""
        return self._request("POST", "/api/v1/settings/radarr", config)

    def update_radarr_server(self, server_id: int, config: dict) -> dict:
        """Update an existing Radarr server."""
        return self._request("PUT", f"/api/v1/settings/radarr/{server_id}", config)

    def delete_radarr_server(self, server_id: int) -> None:
        """Delete a Radarr server."""
        self._request("DELETE", f"/api/v1/settings/radarr/{server_id}")

    def get_sonarr_servers(self) -> list[dict]:
        """Get configured Sonarr servers."""
        result = self._request("GET", "/api/v1/settings/sonarr")
        return result if isinstance(result, list) else []

    def add_sonarr_server(self, config: dict) -> dict:
        """Add a new Sonarr server."""
        return self._request("POST", "/api/v1/settings/sonarr", config)

    def update_sonarr_server(self, server_id: int, config: dict) -> dict:
        """Update an existing Sonarr server."""
        return self._request("PUT", f"/api/v1/settings/sonarr/{server_id}", config)

    def delete_sonarr_server(self, server_id: int) -> None:
        """Delete a Sonarr server."""
        self._request("DELETE", f"/api/v1/settings/sonarr/{server_id}")

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "OverseerrApi":
        return self

    def __exit__(self, *args) -> None:
        self.close()
