#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""FlareSolverr Charm - Cloudflare bypass proxy for Prowlarr."""

import logging
import urllib.error
import urllib.request

import ops
from charms.istio_beacon_k8s.v0.service_mesh import AppPolicy, Endpoint, ServiceMeshConsumer

from charmarr_lib.core import observe_events, reconcilable_events_k8s
from charmarr_lib.core.interfaces import FlareSolverrProvider, FlareSolverrProviderData

logger = logging.getLogger(__name__)

CONTAINER_NAME = "flaresolverr"
PORT = 8191


class FlareSolverrCharm(ops.CharmBase):
    """FlareSolverr Cloudflare bypass proxy charm."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._container = self.unit.get_container(CONTAINER_NAME)

        self._flaresolverr = FlareSolverrProvider(self, "flaresolverr")
        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="flaresolverr",
                    endpoints=[Endpoint(ports=[PORT])],
                ),
            ],
        )

        observe_events(self, reconcilable_events_k8s, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    @property
    def _internal_url(self) -> str:
        """Internal K8s service URL for cross-namespace communication."""
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{PORT}"

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile charm state."""
        if not self._container.can_connect():
            return

        self._configure_pebble()
        self.unit.set_ports(PORT)

        if self._is_workload_ready():
            self._publish_relation_data()

    def _configure_pebble(self) -> None:
        """Configure the Pebble layer for FlareSolverr."""
        log_level = str(self.config.get("log-level", "info")).upper()
        timeout = int(self.config.get("timeout", 60000))

        layer = ops.pebble.Layer(
            {
                "summary": "FlareSolverr layer",
                "services": {
                    "flaresolverr": {
                        "override": "replace",
                        "summary": "FlareSolverr service",
                        "command": "python -u /app/flaresolverr.py",
                        "startup": "enabled",
                        "environment": {
                            "LOG_LEVEL": log_level,
                            "BROWSER_TIMEOUT": str(timeout),
                            "TZ": "UTC",
                        },
                    }
                },
                "checks": {
                    "health": {
                        "override": "replace",
                        "level": "ready",
                        "http": {"url": f"http://localhost:{PORT}/health"},
                        "period": "30s",
                        "timeout": "5s",
                    }
                },
            }
        )

        self._container.add_layer("flaresolverr", layer, combine=True)
        self._container.replan()

    def _publish_relation_data(self) -> None:
        """Publish FlareSolverr URL to related applications."""
        if not self.unit.is_leader():
            return

        data = FlareSolverrProviderData(url=self._internal_url)
        self._flaresolverr.publish_data(data)

    def _is_workload_ready(self) -> bool:
        """Check if FlareSolverr is responding to health checks."""
        try:
            req = urllib.request.Request(f"http://localhost:{PORT}/health", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect all unit statuses. Framework picks the worst."""
        self._collect_pebble_status(event)
        self._collect_workload_status(event)

    def _collect_pebble_status(self, event: ops.CollectStatusEvent) -> None:
        """Check Pebble connectivity."""
        if not self._container.can_connect():
            event.add_status(ops.WaitingStatus("Waiting for Pebble"))

    def _collect_workload_status(self, event: ops.CollectStatusEvent) -> None:
        """Check workload health."""
        if not self._container.can_connect():
            return

        if not self._is_workload_ready():
            event.add_status(ops.WaitingStatus("Starting FlareSolverr"))
        else:
            event.add_status(ops.ActiveStatus())


if __name__ == "__main__":
    ops.main(FlareSolverrCharm)
