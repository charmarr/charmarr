# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Private module for Overseerr charm implementation."""

from _overseerr._api import OverseerrApi, OverseerrApiError
from _overseerr._constants import (
    API_KEY_SECRET_LABEL,
    CONTAINER_NAME,
    DEFAULT_PGID,
    DEFAULT_PUID,
    SERVICE_NAME,
    SETTINGS_FILE,
    WEBUI_PORT,
)

__all__ = [
    "API_KEY_SECRET_LABEL",
    "CONTAINER_NAME",
    "DEFAULT_PGID",
    "DEFAULT_PUID",
    "SERVICE_NAME",
    "SETTINGS_FILE",
    "WEBUI_PORT",
    "OverseerrApi",
    "OverseerrApiError",
]
