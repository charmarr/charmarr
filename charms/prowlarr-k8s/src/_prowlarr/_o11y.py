# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Observability constants for the Prowlarr charm."""

METRICS_CONTAINER_NAME = "scraparr"
METRICS_SERVICE_NAME = "scraparr"
METRICS_PORT = 7100
METRICS_PATH = "/metrics"
SCRAPARR_COMMAND = "python -um scraparr.scraparr"
SCRAPARR_ENV_URL = "PROWLARR_URL"
SCRAPARR_ENV_API_KEY = "PROWLARR_API_KEY"
SCRAPARR_ENV_DETAILED = "PROWLARR_DETAILED"
