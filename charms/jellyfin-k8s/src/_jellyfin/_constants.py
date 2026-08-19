# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Constants for Jellyfin charm."""

CONTAINER_NAME = "jellyfin"
SERVICE_NAME = "jellyfin"
WEBUI_PORT = 8096

# Directory layout under the /config storage mount (LinuxServer image defaults).
CONFIG_DIR = "/config"
DATA_DIR = "/config/data"
CACHE_DIR = "/config/cache"
LOG_DIR = "/config/log"
WEB_DIR = "/usr/share/jellyfin/web"
SYSTEM_XML = "/config/system.xml"

# Binary path in LinuxServer.io image (bypassing s6-overlay).
JELLYFIN_BINARY = "/usr/bin/jellyfin"
FFMPEG_PATH = "/usr/lib/jellyfin-ffmpeg/ffmpeg"

# First-run bootstrap: the charm completes the startup wizard, then mints a
# server-wide API key registered under this app name.
API_KEY_APP_NAME = "charmarr"
API_KEY_SECRET_LABEL = "api-key"
ADMIN_SECRET_LABEL = "admin-credentials"
ADMIN_USERNAME = "charmarr"
