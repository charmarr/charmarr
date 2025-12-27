# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd-specific constants."""

API_KEY_BYTES = 16

CONTAINER_NAME = "sabnzbd"
CONFIG_FILE = "/config/sabnzbd.ini"
API_KEY_SECRET_LABEL = "api-key"

WEBUI_PORT = 8080
API_BASE_PATH = "/api"

SERVICE_NAME = "sabnzbd"
HEALTH_CHECK_URL = f"http://localhost:{WEBUI_PORT}{API_BASE_PATH}?mode=version&output=json"
