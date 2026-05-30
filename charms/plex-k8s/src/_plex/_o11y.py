# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Observability constants for the Plex charm.

The exporter is axsuul/plex-media-server-exporter (Ruby/Puma) as a sidecar
container in the same pod. The sidecar reaches Plex over localhost using the
X-Plex-Token exchanged at server-claim time and stored in Plex's preferences.
"""

METRICS_CONTAINER_NAME = "plex-exporter"
METRICS_SERVICE_NAME = "plex-exporter"
METRICS_PORT = 9594
METRICS_PATH = "/metrics"
EXPORTER_COMMAND = f"bundle exec puma -b tcp://0.0.0.0:{METRICS_PORT}"
EXPORTER_WORKING_DIR = "/srv"
EXPORTER_ENV_ADDR = "PLEX_ADDR"
EXPORTER_ENV_TOKEN = "PLEX_TOKEN"
EXPORTER_ENV_PORT = "PORT"
