# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Private module for Seerr charm implementation."""

from _seerr._api import SeerrApi, SeerrApiError
from _seerr._constants import (
    API_KEY_SECRET_LABEL,
    CONFIG_DIR,
    CONTAINER_NAME,
    DEFAULT_PGID,
    DEFAULT_PUID,
    MEDIA_SERVER_TYPE_JELLYFIN,
    MEDIA_SERVER_TYPE_PLEX,
    MEDIA_SERVER_TYPE_UNSET,
    SERVICE_NAME,
    SETTINGS_FILE,
    WEBUI_PORT,
)

__all__ = [
    "API_KEY_SECRET_LABEL",
    "CONFIG_DIR",
    "CONTAINER_NAME",
    "DEFAULT_PGID",
    "DEFAULT_PUID",
    "MEDIA_SERVER_TYPE_JELLYFIN",
    "MEDIA_SERVER_TYPE_PLEX",
    "MEDIA_SERVER_TYPE_UNSET",
    "SERVICE_NAME",
    "SETTINGS_FILE",
    "WEBUI_PORT",
    "SeerrApi",
    "SeerrApiError",
]
