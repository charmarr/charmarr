# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""qBittorrent-specific utilities."""

from _qbittorrent._api import QBittorrentApi, QBittorrentApiError
from _qbittorrent._constants import (
    CONFIG_FILE,
    CONTAINER_NAME,
    CREDENTIALS_SECRET_LABEL,
    DEFAULT_USERNAME,
    HEALTH_CHECK_URL,
    SERVICE_NAME,
    WEBUI_PORT,
)
from _qbittorrent._credentials import (
    compute_pbkdf2_hash,
    generate_password,
    reconcile_qbittorrent_config,
)
from _qbittorrent._o11y import (
    EXPORTER_COMMAND,
    EXPORTER_ENV_BASE_URL,
    EXPORTER_ENV_PASSWORD,
    EXPORTER_ENV_PORT,
    EXPORTER_ENV_USERNAME,
    METRICS_CONTAINER_NAME,
    METRICS_PATH,
    METRICS_PORT,
    METRICS_SERVICE_NAME,
)

__all__ = [
    "CONFIG_FILE",
    "CONTAINER_NAME",
    "CREDENTIALS_SECRET_LABEL",
    "DEFAULT_USERNAME",
    "EXPORTER_COMMAND",
    "EXPORTER_ENV_BASE_URL",
    "EXPORTER_ENV_PASSWORD",
    "EXPORTER_ENV_PORT",
    "EXPORTER_ENV_USERNAME",
    "HEALTH_CHECK_URL",
    "METRICS_CONTAINER_NAME",
    "METRICS_PATH",
    "METRICS_PORT",
    "METRICS_SERVICE_NAME",
    "SERVICE_NAME",
    "WEBUI_PORT",
    "QBittorrentApi",
    "QBittorrentApiError",
    "compute_pbkdf2_hash",
    "generate_password",
    "reconcile_qbittorrent_config",
]
