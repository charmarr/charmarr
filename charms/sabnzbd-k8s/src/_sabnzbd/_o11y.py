# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Observability constants for the SABnzbd charm.

The exporter is msroest/sabnzbd_exporter (Python) as a sidecar container.
Sidecar reaches SABnzbd over localhost; auth via the existing api-key secret.
"""

METRICS_CONTAINER_NAME = "sabnzbd-exporter"
METRICS_SERVICE_NAME = "sabnzbd-exporter"
METRICS_PORT = 9387
METRICS_PATH = "/metrics"
EXPORTER_COMMAND = "python /sabnzbd_exporter.py"
EXPORTER_ENV_BASEURLS = "SABNZBD_BASEURLS"
EXPORTER_ENV_APIKEYS = "SABNZBD_APIKEYS"
EXPORTER_ENV_PORT = "METRICS_PORT"
