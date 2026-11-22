# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Constants for Prowlarr charm."""

CONTAINER_NAME = "prowlarr"
SERVICE_NAME = "prowlarr"
WEBUI_PORT = 9696
CONFIG_FILE = "/config/config.xml"
API_KEY_SECRET_LABEL = "api-key"
# Durable marker that a forced ApplicationIndexerSync still has to run. Set when
# the Prowlarr API key changes and cleared once the re-push succeeds, so the
# resync survives the workload restart that the rotation triggers.
INDEXER_SYNC_PENDING_FILE = "/config/.indexer-sync-pending"

DEFAULT_PUID = 1000
DEFAULT_PGID = 1000
