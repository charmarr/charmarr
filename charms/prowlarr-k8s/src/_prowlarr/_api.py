# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""API client for Prowlarr (/api/v1)."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from charmarr_lib.core import BaseArrApiClient, MediaManagerConnection


class IndexerProxyType(str, Enum):
    """Prowlarr indexer proxy types."""

    FLARESOLVERR = "FlareSolverr"
    HTTP = "Http"
    SOCKS4 = "Socks4"
    SOCKS5 = "Socks5"


RESPONSE_MODEL_CONFIG = ConfigDict(extra="allow", populate_by_name=True)


class IndexerResponse(BaseModel):
    """Indexer response from Prowlarr API."""

    model_config = RESPONSE_MODEL_CONFIG

    id: int
    name: str
    enable: bool
    protocol: str
    implementation: str


class IndexerProxyResponse(BaseModel):
    """Indexer proxy response from Prowlarr API."""

    model_config = RESPONSE_MODEL_CONFIG

    id: int
    name: str
    implementation: IndexerProxyType
    config_contract: str = Field(alias="configContract")
    tags: list[int] = Field(default_factory=list)


class TagResponse(BaseModel):
    """Tag response from Prowlarr API."""

    model_config = RESPONSE_MODEL_CONFIG

    id: int
    label: str


class FlareSolverrProxyConfig(BaseModel):
    """Configuration for FlareSolverr proxy in Prowlarr."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = "FlareSolverr"
    implementation: IndexerProxyType = IndexerProxyType.FLARESOLVERR
    config_contract: str = Field(default="FlareSolverrSettings", alias="configContract")
    fields: list[dict[str, str]] = Field(default_factory=list)
    tags: list[int] = Field(default_factory=list)

    @classmethod
    def from_url(cls, url: str, tags: list[int] | None = None) -> "FlareSolverrProxyConfig":
        """Create config from FlareSolverr URL."""
        return cls(fields=[{"name": "host", "value": url}], tags=tags or [])


class ProwlarrHostConfigResponse(BaseModel):
    """Host configuration response from Prowlarr API."""

    model_config = RESPONSE_MODEL_CONFIG

    id: int
    bind_address: str = Field(alias="bindAddress")
    port: int
    url_base: str | None = Field(default=None, alias="urlBase")


class ProwlarrApiClient(BaseArrApiClient):
    """API client for Prowlarr (/api/v1).

    Provides methods for managing applications (connections to media managers),
    indexers, and host configuration. Implements MediaIndexerClient protocol.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            api_version="v1",
            timeout=timeout,
            max_retries=max_retries,
        )

    # Applications (MediaIndexerClient protocol methods)

    def get_applications(self) -> list[MediaManagerConnection]:
        """Get all configured applications (media manager connections)."""
        return self._get_validated_list("/applications", MediaManagerConnection)

    def get_application(self, app_id: int) -> dict[str, Any]:
        """Get a single application by ID as raw dict."""
        return self._get(f"/applications/{app_id}")

    def add_application(self, config: dict[str, Any]) -> MediaManagerConnection:
        """Add a new application."""
        return self._post_validated("/applications", config, MediaManagerConnection)

    def update_application(self, app_id: int, config: dict[str, Any]) -> MediaManagerConnection:
        """Update an existing application."""
        config_with_id = {**config, "id": app_id}
        return self._put_validated(
            f"/applications/{app_id}", config_with_id, MediaManagerConnection
        )

    def delete_application(self, app_id: int) -> None:
        """Delete an application."""
        self._delete(f"/applications/{app_id}")

    # Indexers (read-only, user manages via UI)

    def get_indexers(self) -> list[IndexerResponse]:
        """Get all configured indexers."""
        return self._get_validated_list("/indexer", IndexerResponse)

    # Host Config (typed response, raw methods are in BaseArrApiClient)

    def get_host_config(self) -> ProwlarrHostConfigResponse:
        """Get host configuration with typed response."""
        return self._get_validated("/config/host", ProwlarrHostConfigResponse)

    # Indexer Proxies (FlareSolverr)

    def get_indexer_proxies(self) -> list[IndexerProxyResponse]:
        """Get all configured indexer proxies (FlareSolverr instances)."""
        return self._get_validated_list("/indexerProxy", IndexerProxyResponse)

    def add_indexer_proxy(self, config: dict[str, Any]) -> IndexerProxyResponse:
        """Add a new indexer proxy (FlareSolverr)."""
        return self._post_validated("/indexerProxy", config, IndexerProxyResponse)

    def update_indexer_proxy(self, proxy_id: int, config: dict[str, Any]) -> IndexerProxyResponse:
        """Update an existing indexer proxy."""
        config_with_id = {**config, "id": proxy_id}
        return self._put_validated(
            f"/indexerProxy/{proxy_id}", config_with_id, IndexerProxyResponse
        )

    def delete_indexer_proxy(self, proxy_id: int) -> None:
        """Delete an indexer proxy."""
        self._delete(f"/indexerProxy/{proxy_id}")

    # Tags

    def get_or_create_tag(self, label: str) -> TagResponse:
        """Get existing tag by label or create if not exists."""
        for tag in self._get_validated_list("/tag", TagResponse):
            if tag.label == label:
                return tag
        return self._post_validated("/tag", {"label": label}, TagResponse)
