# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Sonarr-specific utilities."""

from _sonarr._constants import (
    API_KEY_SECRET_LABEL,
    CONFIG_FILE,
    CONTAINER_NAME,
    SERVICE_NAME,
    WEBUI_PORT,
)
from _sonarr._o11y import (
    METRICS_CONTAINER_NAME,
    METRICS_PATH,
    METRICS_PORT,
    METRICS_SERVICE_NAME,
    SCRAPARR_COMMAND,
    SCRAPARR_ENV_API_KEY,
    SCRAPARR_ENV_DETAILED,
    SCRAPARR_ENV_URL,
)

__all__ = [
    "API_KEY_SECRET_LABEL",
    "CONFIG_FILE",
    "CONTAINER_NAME",
    "METRICS_CONTAINER_NAME",
    "METRICS_PATH",
    "METRICS_PORT",
    "METRICS_SERVICE_NAME",
    "SCRAPARR_COMMAND",
    "SCRAPARR_ENV_API_KEY",
    "SCRAPARR_ENV_DETAILED",
    "SCRAPARR_ENV_URL",
    "SERVICE_NAME",
    "WEBUI_PORT",
]
