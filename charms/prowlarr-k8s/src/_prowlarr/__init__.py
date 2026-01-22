# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Prowlarr-specific utilities."""

from _prowlarr._api import (
    FlareSolverrProxyConfig,
    IndexerProxyResponse,
    IndexerProxyType,
    IndexerResponse,
    ProwlarrApiClient,
    ProwlarrHostConfigResponse,
    TagResponse,
)
from _prowlarr._constants import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    DEFAULT_PGID,
    DEFAULT_PUID,
    SERVICE_NAME,
    WEBUI_PORT,
)

__all__ = [
    "API_KEY_SECRET_LABEL",
    "CONFIG_FILE",
    "CONTAINER_NAME",
    "DEFAULT_PGID",
    "DEFAULT_PUID",
    "SERVICE_NAME",
    "WEBUI_PORT",
    "FlareSolverrProxyConfig",
    "IndexerProxyResponse",
    "IndexerProxyType",
    "IndexerResponse",
    "ProwlarrApiClient",
    "ProwlarrHostConfigResponse",
    "TagResponse",
]
