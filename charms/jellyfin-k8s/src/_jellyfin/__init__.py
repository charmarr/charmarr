# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Jellyfin-specific utilities."""

from _jellyfin._api import JellyfinApi, JellyfinApiError, VirtualFolder
from _jellyfin._config import enable_metrics, is_startup_wizard_completed
from _jellyfin._constants import (
    ADMIN_SECRET_LABEL,
    ADMIN_USERNAME,
    API_KEY_APP_NAME,
    API_KEY_SECRET_LABEL,
    CACHE_DIR,
    CONFIG_DIR,
    CONTAINER_NAME,
    DATA_DIR,
    FFMPEG_PATH,
    JELLYFIN_BINARY,
    LOG_DIR,
    SERVICE_NAME,
    SYSTEM_XML,
    WEB_DIR,
    WEBUI_PORT,
)
from _jellyfin._libraries import collection_type, library_name
from _jellyfin._o11y import METRICS_PATH, METRICS_PORT

__all__ = [
    "ADMIN_SECRET_LABEL",
    "ADMIN_USERNAME",
    "API_KEY_APP_NAME",
    "API_KEY_SECRET_LABEL",
    "CACHE_DIR",
    "CONFIG_DIR",
    "CONTAINER_NAME",
    "DATA_DIR",
    "FFMPEG_PATH",
    "JELLYFIN_BINARY",
    "LOG_DIR",
    "METRICS_PATH",
    "METRICS_PORT",
    "SERVICE_NAME",
    "SYSTEM_XML",
    "WEBUI_PORT",
    "WEB_DIR",
    "JellyfinApi",
    "JellyfinApiError",
    "VirtualFolder",
    "collection_type",
    "enable_metrics",
    "is_startup_wizard_completed",
    "library_name",
]
