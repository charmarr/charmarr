# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Observability constants for the qBittorrent charm.

The exporter is martabal/qbittorrent-exporter (Go binary) as a sidecar
container in the same pod as qBittorrent. Sidecar reaches qBittorrent over
localhost; auth credentials come from the existing Juju secret.
"""

METRICS_CONTAINER_NAME = "qbittorrent-exporter"
METRICS_SERVICE_NAME = "qbittorrent-exporter"
METRICS_PORT = 8090
METRICS_PATH = "/metrics"
EXPORTER_COMMAND = "/go/bin/qbittorrent-exporter"
EXPORTER_ENV_BASE_URL = "QBITTORRENT_BASE_URL"
EXPORTER_ENV_USERNAME = "QBITTORRENT_USERNAME"
EXPORTER_ENV_PASSWORD = "QBITTORRENT_PASSWORD"
EXPORTER_ENV_PORT = "EXPORTER_PORT"
