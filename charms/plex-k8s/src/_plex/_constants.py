# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Constants for Plex charm."""

CONTAINER_NAME = "plex"
SERVICE_NAME = "plex"
WEBUI_PORT = 32400

# Plex stores config in APPLICATION_SUPPORT_DIR/Plex Media Server/
# We set APPLICATION_SUPPORT_DIR, Plex creates the "Plex Media Server" subdir
PLEX_DATA_DIR = "/config/Library/Application Support"
PREFERENCES_FILE = f"{PLEX_DATA_DIR}/Plex Media Server/Preferences.xml"

# Binary path in LinuxServer.io image (bypassing s6-overlay)
PLEX_BINARY = '"/usr/lib/plexmediaserver/Plex Media Server"'
