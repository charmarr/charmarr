# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Plex-specific utilities."""

from _plex._api import (
    PlexApi,
    PlexApiConnectionError,
    PlexApiError,
    PlexApiResponseError,
    PlexLibrary,
)
from _plex._claim import (
    ensure_custom_connection,
    exchange_claim_token,
    extract_machine_identifier,
    extract_online_token,
    inject_online_token,
)
from _plex._constants import (
    CONTAINER_NAME,
    PLEX_BINARY,
    PLEX_DATA_DIR,
    PREFERENCES_FILE,
    SERVICE_NAME,
    WEBUI_PORT,
)

__all__ = [
    "CONTAINER_NAME",
    "PLEX_BINARY",
    "PLEX_DATA_DIR",
    "PREFERENCES_FILE",
    "SERVICE_NAME",
    "WEBUI_PORT",
    "PlexApi",
    "PlexApiConnectionError",
    "PlexApiError",
    "PlexApiResponseError",
    "PlexLibrary",
    "ensure_custom_connection",
    "exchange_claim_token",
    "extract_machine_identifier",
    "extract_online_token",
    "inject_online_token",
]
