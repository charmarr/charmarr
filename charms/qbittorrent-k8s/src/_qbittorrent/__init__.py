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
    build_qbittorrent_config,
    compute_pbkdf2_hash,
    generate_password,
)

__all__ = [
    "CONFIG_FILE",
    "CONTAINER_NAME",
    "CREDENTIALS_SECRET_LABEL",
    "DEFAULT_USERNAME",
    "HEALTH_CHECK_URL",
    "SERVICE_NAME",
    "WEBUI_PORT",
    "QBittorrentApi",
    "QBittorrentApiError",
    "build_qbittorrent_config",
    "compute_pbkdf2_hash",
    "generate_password",
]
