# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Constants for Plex charm."""

CONTAINER_NAME = "plex"
SERVICE_NAME = "plex"
WEBUI_PORT = 32400

# Plex stores config in a nested path under /config
PLEX_DATA_DIR = "/config/Library/Application Support/Plex Media Server"
PREFERENCES_FILE = f"{PLEX_DATA_DIR}/Preferences.xml"

# Binary path in LinuxServer.io image (bypassing s6-overlay)
PLEX_BINARY = '"/usr/lib/plexmediaserver/Plex Media Server"'
