# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Constants for Seerr charm."""

CONTAINER_NAME = "seerr"
SERVICE_NAME = "seerr"
WEBUI_PORT = 5055

CONFIG_DIR = "/app/config"
SETTINGS_FILE = "/app/config/settings.json"
API_KEY_SECRET_LABEL = "api-key"

# Hardcoded PUID/PGID since Seerr doesn't require storage relation.
# See ADR-015 Pebble/LinuxServer pattern. Upstream image ships UID 1000
# in /etc/passwd, so ensure_pebble_user() is unnecessary (ADR-016).
DEFAULT_PUID = 1000
DEFAULT_PGID = 1000
