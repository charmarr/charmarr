# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd-specific utilities."""

from _sabnzbd._api import SABnzbdApi, SABnzbdApiError
from _sabnzbd._constants import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    HEALTH_CHECK_URL,
    SERVICE_NAME,
    WEBUI_PORT,
)
from _sabnzbd._credentials import build_sabnzbd_config, generate_api_key

__all__ = [
    "API_KEY_SECRET_LABEL",
    "CONFIG_FILE",
    "CONTAINER_NAME",
    "HEALTH_CHECK_URL",
    "SERVICE_NAME",
    "WEBUI_PORT",
    "SABnzbdApi",
    "SABnzbdApiError",
    "build_sabnzbd_config",
    "generate_api_key",
]
