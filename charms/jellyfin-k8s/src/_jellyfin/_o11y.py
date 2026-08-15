# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Observability constants for the Jellyfin charm.

Jellyfin exposes a native Prometheus endpoint on its main HTTP port once
``<EnableMetrics>true</EnableMetrics>`` is set in system.xml. There is no
exporter sidecar; Prometheus scrapes the workload directly.
"""

from _jellyfin._constants import WEBUI_PORT

METRICS_PORT = WEBUI_PORT
METRICS_PATH = "/metrics"
