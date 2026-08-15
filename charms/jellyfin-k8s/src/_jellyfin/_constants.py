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
