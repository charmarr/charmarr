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
from _sabnzbd._credentials import reconcile_sabnzbd_config
from _sabnzbd._o11y import (
    EXPORTER_COMMAND,
    EXPORTER_ENV_APIKEYS,
    EXPORTER_ENV_BASEURLS,
    EXPORTER_ENV_PORT,
    METRICS_CONTAINER_NAME,
    METRICS_PATH,
    METRICS_PORT,
    METRICS_SERVICE_NAME,
)

__all__ = [
    "API_KEY_SECRET_LABEL",
    "CONFIG_FILE",
    "CONTAINER_NAME",
    "EXPORTER_COMMAND",
    "EXPORTER_ENV_APIKEYS",
    "EXPORTER_ENV_BASEURLS",
    "EXPORTER_ENV_PORT",
    "HEALTH_CHECK_URL",
    "METRICS_CONTAINER_NAME",
    "METRICS_PATH",
    "METRICS_PORT",
    "METRICS_SERVICE_NAME",
    "SERVICE_NAME",
    "WEBUI_PORT",
    "SABnzbdApi",
    "SABnzbdApiError",
    "reconcile_sabnzbd_config",
]
