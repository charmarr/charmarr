# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Constants for Overseerr charm."""

CONTAINER_NAME = "overseerr"
SERVICE_NAME = "overseerr"
WEBUI_PORT = 5055

SETTINGS_FILE = "/config/settings.json"
API_KEY_SECRET_LABEL = "api-key"

CONFIG_DIR = "/config"
EXPORT_TARBALL_PATH = "/config/overseerr-export.tgz"

DEPRECATION_MESSAGE = "Deprecated - migrate to seerr-k8s"
DEPRECATION_LOG = (
    "overseerr-k8s is DEPRECATED. Upstream Overseerr has merged with Jellyseerr "
    "into Seerr. Migrate to seerr-k8s. Run 'juju run <overseerr-unit> export-config' "
    "to start. See https://docs.seerr.dev/migration-guide/"
)

# Hardcoded PUID/PGID since Overseerr doesn't require storage relation
# See ADR-015 Pebble/LinuxServer pattern
DEFAULT_PUID = 1000
DEFAULT_PGID = 1000
