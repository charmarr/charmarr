# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""qBittorrent-specific constants."""

PBKDF2_ITERATIONS = 100000
SALT_BYTES = 16
PASSWORD_BYTES = 24
DEFAULT_USERNAME = "charmarr"

CONTAINER_NAME = "qbittorrent"
CONFIG_DIR = "/config/qBittorrent/config"
CONFIG_FILE = f"{CONFIG_DIR}/qBittorrent.conf"
CREDENTIALS_SECRET_LABEL = "credentials"

WEBUI_PORT = 8080
API_BASE_PATH = "/api/v2"

SERVICE_NAME = "qbittorrent"
HEALTH_CHECK_URL = f"http://localhost:{WEBUI_PORT}{API_BASE_PATH}/app/version"
