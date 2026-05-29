# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Observability constants for the Radarr charm.

The exporter is a scraparr sidecar container in the same pod as the Radarr
workload. The sidecar reaches Radarr over localhost; the workload API key is
passed via environment variable from the existing Juju secret.
"""

METRICS_CONTAINER_NAME = "scraparr"
METRICS_SERVICE_NAME = "scraparr"
METRICS_PORT = 7100
METRICS_PATH = "/metrics"
SCRAPARR_COMMAND = "python -um scraparr.scraparr"
SCRAPARR_ENV_URL = "RADARR_URL"
SCRAPARR_ENV_API_KEY = "RADARR_API_KEY"
