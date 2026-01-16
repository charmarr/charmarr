# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Plex API client for library management."""

import logging
from dataclasses import dataclass
from types import TracebackType
from typing import Self
from urllib.parse import quote_plus, urlencode
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)


class PlexApiError(Exception):
    """Base exception for Plex API errors."""

    pass


class PlexApiConnectionError(PlexApiError):
    """Connection error to Plex API."""

    pass


class PlexApiResponseError(PlexApiError):
    """Unexpected response from Plex API."""

    pass


@dataclass
class PlexLibrary:
    """Represents a Plex library section."""

    key: str
    title: str
    type: str
    location: list[str]


class PlexApi:
    """Plex Media Server API client for library management."""

    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client: httpx.Client | None = None

    def __enter__(self) -> Self:
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "X-Plex-Token": self._token,
                "Accept": "application/xml",
            },
            timeout=30.0,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client:
            self._client.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make HTTP request to Plex API."""
        if not self._client:
            raise PlexApiError("Client not initialized - use context manager")

        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise PlexApiResponseError(f"HTTP {e.response.status_code}: {e}") from e
        except httpx.RequestError as e:
            raise PlexApiConnectionError(f"Connection failed: {e}") from e

    def get_libraries(self) -> list[PlexLibrary]:
        """Get all library sections."""
        response = self._request("GET", "/library/sections")
        root = ElementTree.fromstring(response.text)

        libraries = []
        for directory in root.findall(".//Directory"):
            locations = [loc.get("path", "") for loc in directory.findall("Location")]
            libraries.append(
                PlexLibrary(
                    key=directory.get("key", ""),
                    title=directory.get("title", ""),
                    type=directory.get("type", ""),
                    location=locations,
                )
            )
        return libraries

    def library_exists_for_path(self, path: str) -> bool:
        """Check if a library exists for the given path."""
        libraries = self.get_libraries()
        return any(path in lib.location for lib in libraries)

    def create_library(
        self,
        name: str,
        library_type: str,
        location: str,
        agent: str | None = None,
        scanner: str | None = None,
        language: str = "en-US",
    ) -> None:
        """Create a new library section.

        Args:
            name: Library display name
            library_type: "movie" or "show"
            location: Path to media folder
            agent: Plex agent (defaults to new Plex agent for type)
            scanner: Scanner name (defaults to appropriate scanner for type)
            language: Language code (default: en-US)
        """
        if agent is None:
            agent = "tv.plex.agents.movie" if library_type == "movie" else "tv.plex.agents.series"

        if scanner is None:
            scanner = "Plex Movie" if library_type == "movie" else "Plex TV Series"

        params = {
            "name": name,
            "type": library_type,
            "agent": agent,
            "scanner": scanner,
            "language": language,
            "location": location,
        }

        path = f"/library/sections?{urlencode(params, quote_via=quote_plus)}"
        self._request("POST", path)
        logger.info("Created Plex library: %s at %s", name, location)

    def is_server_ready(self) -> bool:
        """Check if Plex server is ready and responding."""
        try:
            self._request("GET", "/identity")
            return True
        except PlexApiError:
            return False
