# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Seerr API client."""

from typing import Any

import httpx

from _seerr._constants import MEDIA_SERVER_TYPE_JELLYFIN


class SeerrApiError(Exception):
    """Base exception for Seerr API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SeerrApi:
    """Seerr API client.

    Uses X-Api-Key header authentication. Endpoints under /api/v1/ are
    backwards-compatible with Overseerr (ADR-016).
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(
            timeout=timeout,
            headers={"X-Api-Key": api_key},
        )

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        url = self._url(path)
        try:
            if method == "GET":
                response = self._client.get(url, params=params)
            elif method == "POST":
                response = self._client.post(url, json=json_data, params=params)
            elif method == "PUT":
                response = self._client.put(url, json=json_data, params=params)
            elif method == "DELETE":
                response = self._client.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json() if response.content else {}
        except httpx.HTTPStatusError as e:
            raise SeerrApiError(f"API request failed: {e}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise SeerrApiError(f"Request failed: {e}") from e

    def get_status(self) -> dict:
        """Get Seerr status (health check)."""
        return self._request("GET", "/api/v1/status")

    def get_request_counts(self) -> dict:
        """Get request counts by status (for SLI gauges).

        Returns a dict like ``{"pending": 5, "approved": 10, "declined": 2,
        "processing": 3, "available": 100, "movie": 80, "tv": 20}`` with
        the request-bucket counts seerr currently tracks.
        """
        result = self._request("GET", "/api/v1/request/count")
        return result if isinstance(result, dict) else {}

    def is_initialized(self) -> bool:
        """Whether Seerr has finished first-run setup.

        `/auth/me` starts answering as soon as the administrator account
        exists, which is before setup is complete, so it cannot be used here.
        """
        try:
            result = self._request("GET", "/api/v1/settings/public")
        except SeerrApiError:
            return False
        return bool(result.get("initialized", False)) if isinstance(result, dict) else False

    def jellyfin_setup(
        self,
        hostname: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = False,
        url_base: str = "",
    ) -> dict:
        """Create the Seerr admin account backed by a Jellyfin account.

        Unauthenticated while no Seerr user exists, which makes this the
        first-run setup call rather than a login. Seerr records the server
        details and mints itself a Jellyfin API token as a side effect. The
        account must be a Jellyfin administrator or the call is rejected.

        No email is sent: Seerr falls back to the Jellyfin username, which
        beats inventing an address that does not resolve.

        `serverType` is mandatory on first run. Seerr rejects the call with
        a bare `NO_ADMIN_USER` if it is absent, which reads like a Jellyfin
        permissions problem but is not.
        """
        return self._request(
            "POST",
            "/api/v1/auth/jellyfin",
            json_data={
                "username": username,
                "password": password,
                "hostname": hostname,
                "port": port,
                "useSsl": use_ssl,
                "urlBase": url_base,
                "serverType": MEDIA_SERVER_TYPE_JELLYFIN,
            },
        )

    def sync_jellyfin_libraries(self) -> list[dict]:
        """Refresh the library list from Jellyfin and return it.

        Seerr answers 404 when the Jellyfin server has no libraries at all,
        which is an ordinary state on a fresh deployment, not a failure.
        """
        try:
            result = self._request(
                "GET", "/api/v1/settings/jellyfin/library", params={"sync": "true"}
            )
        except SeerrApiError as e:
            if e.status_code == 404:
                return []
            raise
        return result if isinstance(result, list) else []

    def enable_jellyfin_libraries(self, library_ids: list[str]) -> None:
        """Enable exactly these libraries; any library omitted is disabled."""
        self._request(
            "GET",
            "/api/v1/settings/jellyfin/library",
            params={"enable": ",".join(library_ids)},
        )

    def initialize(self) -> None:
        """Take Seerr out of setup mode."""
        self._request("POST", "/api/v1/settings/initialize")

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

    def __enter__(self) -> "SeerrApi":
        return self

    def __exit__(self, *args) -> None:
        self.close()
