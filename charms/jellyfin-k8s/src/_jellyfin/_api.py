# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Jellyfin API client for first-run bootstrap and library management."""

import logging
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)


class JellyfinApiError(Exception):
    """Base exception for Jellyfin API errors."""


class JellyfinApiConnectionError(JellyfinApiError):
    """Connection error to Jellyfin API."""


class JellyfinApiResponseError(JellyfinApiError):
    """Unexpected response from Jellyfin API."""


@dataclass
class VirtualFolder:
    """A Jellyfin library (virtual folder)."""

    name: str
    collection_type: str
    locations: list[str] = field(default_factory=list)


class JellyfinApi:
    """Jellyfin API client covering startup wizard, API keys, and libraries."""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._client: httpx.Client | None = None

    def __enter__(self) -> Self:
        self._client = httpx.Client(base_url=self._base_url, timeout=self._timeout)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client:
            self._client.close()

    def _auth_header(self, token: str | None = None) -> dict[str, str]:
        """Build the MediaBrowser authorization header.

        With a token this authenticates the request; without one it only
        identifies the client, which is what /Users/AuthenticateByName needs.
        """
        token = token or self._token
        if token:
            return {"Authorization": f'MediaBrowser Token="{token}"'}
        return {
            "Authorization": (
                'MediaBrowser Client="charmarr", Device="juju", '
                'DeviceId="charmarr-jellyfin-k8s", Version="1.0.0"'
            )
        }

    def _request(
        self, method: str, path: str, token: str | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Make an authenticated HTTP request to the Jellyfin API."""
        if not self._client:
            raise JellyfinApiError("Client not initialized - use context manager")

        headers = {**self._auth_header(token), **kwargs.pop("headers", {})}
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise JellyfinApiResponseError(f"HTTP {e.response.status_code}: {e}") from e
        except httpx.RequestError as e:
            raise JellyfinApiConnectionError(f"Connection failed: {e}") from e

    def get_public_info(self) -> dict[str, Any]:
        """Get unauthenticated server info."""
        return self._request("GET", "/System/Info/Public").json()

    def is_ready(self) -> bool:
        """Check if the Jellyfin server is responding."""
        try:
            self.get_public_info()
            return True
        except JellyfinApiError:
            return False

    def is_setup_complete(self) -> bool:
        """Check whether the startup wizard has been completed."""
        return bool(self.get_public_info().get("StartupWizardCompleted", False))

    def complete_setup_wizard(
        self,
        username: str,
        password: str,
        ui_culture: str = "en-US",
        metadata_country_code: str = "US",
        preferred_metadata_language: str = "en",
    ) -> None:
        """Run the startup wizard to create the admin user.

        These endpoints are anonymous but Jellyfin rejects them once the wizard
        is complete, so this is strictly a first-run operation.
        """
        self._request(
            "POST",
            "/Startup/Configuration",
            json={
                "UICulture": ui_culture,
                "MetadataCountryCode": metadata_country_code,
                "PreferredMetadataLanguage": preferred_metadata_language,
            },
        )
        # POST /Startup/User 404s unless the default user has been read once
        # first - Jellyfin only materializes it on GET. Verified on 10.11.11.
        self._request("GET", "/Startup/User")
        self._request("POST", "/Startup/User", json={"Name": username, "Password": password})
        self._request(
            "POST",
            "/Startup/RemoteAccess",
            json={"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False},
        )
        self._request("POST", "/Startup/Complete")
        logger.info("Completed Jellyfin startup wizard for admin user %s", username)

    def authenticate(self, username: str, password: str) -> str:
        """Authenticate as a user and return a session access token."""
        response = self._request(
            "POST",
            "/Users/AuthenticateByName",
            json={"Username": username, "Pw": password},
        )
        token = response.json().get("AccessToken")
        if not token:
            raise JellyfinApiResponseError("AuthenticateByName returned no AccessToken")
        return str(token)

    def list_api_keys(self, app_name: str, token: str | None = None) -> list[str]:
        """Return the access tokens of every API key registered under app_name."""
        response = self._request("GET", "/Auth/Keys", token=token)
        return [
            str(item["AccessToken"])
            for item in response.json().get("Items", [])
            if item.get("AppName") == app_name
        ]

    def get_api_key(self, app_name: str, token: str | None = None) -> str | None:
        """Return the access token of the API key registered under app_name."""
        keys = self.list_api_keys(app_name, token=token)
        return keys[0] if keys else None

    def delete_api_key(self, api_key: str, token: str | None = None) -> None:
        """Revoke an API key by its access token."""
        self._request("DELETE", f"/Auth/Keys/{api_key}", token=token)

    def ensure_api_key(self, app_name: str, token: str | None = None) -> str:
        """Create the API key for app_name if absent, and return it.

        Jellyfin's key creation endpoint returns 204 with no body, so the key
        has to be read back from the key list.
        """
        if existing := self.get_api_key(app_name, token=token):
            return existing

        self._request("POST", "/Auth/Keys", token=token, params={"app": app_name})
        api_key = self.get_api_key(app_name, token=token)
        if not api_key:
            raise JellyfinApiResponseError(f"API key '{app_name}' missing after creation")
        logger.info("Created Jellyfin API key for %s", app_name)
        return api_key

    def rotate_api_key(self, app_name: str, current: str, token: str | None = None) -> str:
        """Mint a replacement key for app_name and revoke the current one.

        The replacement is created before the old key is revoked, so a failure
        partway through leaves the existing key working.
        """
        self._request("POST", "/Auth/Keys", token=token, params={"app": app_name})
        replacement = next(
            (key for key in self.list_api_keys(app_name, token=token) if key != current), None
        )
        if not replacement:
            raise JellyfinApiResponseError(f"API key '{app_name}' missing after rotation")

        self.delete_api_key(current, token=token)
        logger.info("Rotated Jellyfin API key for %s", app_name)
        return replacement

    def get_virtual_folders(self) -> list[VirtualFolder]:
        """Get all configured libraries."""
        response = self._request("GET", "/Library/VirtualFolders")
        return [
            VirtualFolder(
                name=item.get("Name", ""),
                collection_type=item.get("CollectionType", ""),
                locations=list(item.get("Locations", [])),
            )
            for item in response.json()
        ]

    def create_virtual_folder(self, name: str, collection_type: str, path: str) -> None:
        """Create a library pointing at a single path.

        Jellyfin does not deduplicate on create - posting the same name twice
        yields "Name2" - so callers must check for existing libraries first.
        Metadata providers are off by default on API-created libraries, hence
        the explicit LibraryOptions.
        """
        self._request(
            "POST",
            "/Library/VirtualFolders",
            params={"name": name, "collectionType": collection_type, "refreshLibrary": "true"},
            json={
                "LibraryOptions": {
                    "PathInfos": [{"Path": path}],
                    "EnableInternetProviders": True,
                    "EnableRealtimeMonitor": True,
                }
            },
        )
        logger.info("Created Jellyfin library '%s' (%s) at %s", name, collection_type, path)
