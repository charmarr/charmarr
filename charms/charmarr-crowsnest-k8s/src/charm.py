#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr Crowsnest Charm - workloadless cross-cutting observability."""

import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import httpx
import ops
from charmlibs.interfaces.sloth import SlothProvider
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.grafana_k8s.v0.grafana_source import GrafanaSourceProvider
from charms.istio_beacon_k8s.v0.service_mesh import (
    AppPolicy,
    Endpoint,
    ServiceMeshConsumer,
    UnitPolicy,
)
from charms.istio_ingress_k8s.v0.istio_ingress_route import (
    BackendRef,
    HTTPPathMatch,
    HTTPPathMatchType,
    HTTPRoute,
    HTTPRouteMatch,
    IstioIngressRouteConfig,
    IstioIngressRouteRequirer,
    Listener,
    ProtocolType,
)
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider

from charmarr_lib.core import (
    CharmarrTopology,
    CharmarrTopologyRelation,
    observe_events,
    reconcilable_events_k8s_workloadless,
)
from charmarr_lib.core.interfaces import CrowsnestRequirer

logger = logging.getLogger(__name__)

SLO_DIR = Path(__file__).parent / "slos"
GRAPH_DAEMON_SCRIPT = Path(__file__).parent / "_graph_daemon.py"

GRAPH_PORT = 9098
INGRESS_PORT = 80
GRAPH_PID_FILE = Path("/tmp/charmarr-graph.pid")
GRAPH_DATA_FILE = Path("/tmp/charmarr-graph.json")
GRAPH_SCRIPT_FILE = Path("/tmp/charmarr-graph-server.py")

POLL_TIMEOUT = 2.0

_EDGE_LINE_RE = re.compile(r"^charmarr_relation_edge\{([^}]*)\} 1")
_BOUND_LINE_RE = re.compile(r"^charmarr_relation_bound\{([^}]*)\} (\d+)")
_LABEL_RE = re.compile(r'(\w+)="([^"]*)"')

GRAFANA_DATASOURCE_TYPE = "hamedkarbasi93-nodegraphapi-datasource"


class CharmarrCrowsnestCharm(ops.CharmBase):
    """Workloadless observability producer: alerts, dashboards, SLOs."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        self._topology = CharmarrTopology(
            self,
            relations=[
                CharmarrTopologyRelation("sloth", role="provides", required=False),
            ],
        )
        self._metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[self._topology.scrape_job],
        )
        self._grafana_dashboards = GrafanaDashboardProvider(self)
        self._log_forwarder = LogForwarder(self, relation_name="logging")
        self._charm_tracing = ops.tracing.Tracing(self, tracing_relation_name="charm-tracing")
        self._sloth = SlothProvider(self)
        self._fleet = CrowsnestRequirer(self, "crowsnest")
        self._ingress = IstioIngressRouteRequirer(self, relation_name="istio-ingress-route")
        # The nodegraph-api plugin uses a hardcoded proxy route `/nodegraphds`
        # in its plugin.json that templates from `jsonData.url`. Without that
        # field populated, Grafana renders the route URL as empty and the
        # proxy fails with "unsupported protocol scheme". So we publish the
        # URL into BOTH the top-level url (for the datasource UI) and
        # jsonData via extra_fields (for the plugin's runtime proxy).
        self._grafana_source = GrafanaSourceProvider(
            self,
            source_type=GRAFANA_DATASOURCE_TYPE,
            source_url=self._source_url(),
            extra_fields={"url": self._source_url()},
        )

        self._service_mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="grafana-source",
                    endpoints=[Endpoint(ports=[GRAPH_PORT])],
                ),
                UnitPolicy(
                    relation="metrics-endpoint",
                    ports=[self._topology.port, GRAPH_PORT],
                ),
            ],
        )

        self._slo_load_error: str | None = None

        observe_events(self, reconcilable_events_k8s_workloadless, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    def _source_url(self) -> str:
        """Pick the most-external URL where this charm's HTTP endpoints are reachable.

        Prefer the istio-ingress-published external host when wired (it's
        addressable from outside the cluster). Otherwise fall back to the
        in-cluster Service FQDN, which works for same-cluster consumers.
        """
        if self._ingress.external_host:
            scheme = "https" if self._ingress.tls_enabled else "http"
            return f"{scheme}://{self._ingress.external_host}/{self.app.name}"
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{GRAPH_PORT}"

    def _load_slo_catalog(self) -> str | None:
        """Concatenate all `src/slos/*.yaml` into one multi-doc YAML payload.

        Adding a new SLO is "drop a YAML in src/slos/" - no charm code change.
        """
        if not SLO_DIR.is_dir():
            logger.warning("SLO directory %s does not exist", SLO_DIR)
            return None

        files = sorted(SLO_DIR.glob("*.yaml"))
        if not files:
            logger.info("No SLO files found in %s", SLO_DIR)
            return None

        documents = [f.read_text().strip() for f in files]
        return "\n---\n".join(documents)

    def _build_aggregate_graph(self) -> dict:
        """Poll each fleet member's topology endpoint and aggregate.

        Fleet members are discovered dynamically via the `crowsnest`
        relation; each provider publishes its in-cluster topology URL.
        Failures to reach any individual member are logged and skipped -
        the graph reflects what's reachable now.

        Returns nodes + edges in the `nodegraph-api` plugin's expected
        format.
        """
        edges_set: set[tuple[str, str, str]] = set()
        bound_by_app: dict[str, dict[str, int]] = defaultdict(
            lambda: {"bound": 0, "req_unbound": 0, "opt_unbound": 0}
        )
        missing_by_app: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: {"required": [], "optional": []}
        )
        reachable_apps: set[str] = set()

        members = self._fleet.get_providers()

        with httpx.Client(timeout=POLL_TIMEOUT) as client:
            for member in members:
                url = member.topology_url
                app = url.split("//", 1)[-1].split(".", 1)[0]
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    payload = response.text
                except httpx.HTTPError as e:
                    logger.debug("topology poll for %s (%s) failed: %s", app, url, e)
                    continue

                reachable_apps.add(app)
                for line in payload.splitlines():
                    if edge_match := _EDGE_LINE_RE.match(line):
                        labels = dict(_LABEL_RE.findall(edge_match.group(1)))
                        from_app = labels.get("from_app", "")
                        to_app = labels.get("to_app", "")
                        relation = labels.get("relation", "")
                        if from_app and to_app and relation:
                            edges_set.add((from_app, relation, to_app))
                    elif bound_match := _BOUND_LINE_RE.match(line):
                        labels = dict(_LABEL_RE.findall(bound_match.group(1)))
                        required = labels.get("required") == "true"
                        bound = bound_match.group(2) == "1"
                        relation_name = labels.get("relation", "")
                        if bound:
                            bound_by_app[app]["bound"] += 1
                        elif required:
                            bound_by_app[app]["req_unbound"] += 1
                            missing_by_app[app]["required"].append(relation_name)
                        else:
                            bound_by_app[app]["opt_unbound"] += 1
                            missing_by_app[app]["optional"].append(relation_name)

        all_apps = reachable_apps | {a for edge in edges_set for a in (edge[0], edge[2])}

        # arc__* values must sum to 1 per Grafana node graph docs - raw
        # counts cause the panel to silently drop all but the first arc.
        # Three colors:
        #   green  = required relations that are wired
        #   red    = required relations declared but unbound (real breakage)
        #   yellow = optional relations declared but unbound (informational)
        def _arcs(app: str) -> tuple[float, float, float]:
            if app not in reachable_apps:
                return (0.0, 1.0, 0.0)
            counts = bound_by_app[app]
            total = counts["bound"] + counts["req_unbound"] + counts["opt_unbound"]
            if total == 0:
                return (1.0, 0.0, 0.0)
            return (
                counts["bound"] / total,
                counts["req_unbound"] / total,
                counts["opt_unbound"] / total,
            )

        nodes = []
        for app in sorted(all_apps):
            bound_arc, missing_arc, optional_arc = _arcs(app)
            req_missing = sorted(missing_by_app[app]["required"])
            opt_missing = sorted(missing_by_app[app]["optional"])
            nodes.append(
                {
                    "id": app,
                    "mainstat": app,
                    "title": "" if app in reachable_apps else "unreachable",
                    "arc__bound": bound_arc,
                    "arc__missing": missing_arc,
                    "arc__optional": optional_arc,
                    "detail__missing_required": ", ".join(req_missing),
                    "detail__missing_optional": ", ".join(opt_missing),
                }
            )

        edges = [
            {
                "id": f"{from_app}->{relation}->{to_app}",
                "source": from_app,
                "target": to_app,
                "mainstat": relation,
            }
            for from_app, relation, to_app in sorted(edges_set)
        ]

        return {"nodes": nodes, "edges": edges}

    def _write_graph_file(self) -> None:
        try:
            graph = self._build_aggregate_graph()
        except Exception:
            logger.exception("Failed to aggregate topology graph")
            return
        GRAPH_DATA_FILE.write_text(json.dumps(graph))

    def _ensure_graph_daemon_running(self) -> None:
        if self._pid_alive(self._read_graph_pid()):
            return

        GRAPH_SCRIPT_FILE.write_text(GRAPH_DAEMON_SCRIPT.read_text())

        # `start_new_session=True` is LOAD-BEARING for the same reason as the
        # topology daemon - detaches the child from the charm hook's process
        # group so it survives hook exit. See charmarr_lib.core._topology.
        proc = subprocess.Popen(
            [sys.executable, str(GRAPH_SCRIPT_FILE), str(GRAPH_PORT), str(GRAPH_DATA_FILE)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        GRAPH_PID_FILE.write_text(str(proc.pid))
        logger.info("Spawned charmarr-graph aggregator on port %d (pid=%d)", GRAPH_PORT, proc.pid)

    def _read_graph_pid(self) -> int | None:
        try:
            return int(GRAPH_PID_FILE.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _pid_alive(self, pid: int | None) -> bool:
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return False
        return True

    def _configure_ingress(self) -> None:
        """Submit an istio-ingress route mapping `/<app-name>/*` to the graph daemon."""
        if not self.unit.is_leader():
            return
        if not self.model.get_relation("istio-ingress-route"):
            return

        listener = Listener(port=INGRESS_PORT, protocol=ProtocolType.HTTP)
        config = IstioIngressRouteConfig(
            model=self.model.name,
            listeners=[listener],
            http_routes=[
                HTTPRoute(
                    name=self.app.name,
                    listener=listener,
                    matches=[
                        HTTPRouteMatch(
                            path=HTTPPathMatch(
                                type=HTTPPathMatchType.PathPrefix,
                                value=f"/{self.app.name}",
                            )
                        )
                    ],
                    backends=[BackendRef(service=self.app.name, port=GRAPH_PORT)],
                ),
            ],
        )
        self._ingress.submit_config(config)

    def _reconcile(self, _: ops.EventBase) -> None:
        """Refresh topology, graph aggregator, ingress, and SLO catalog."""
        self._topology.reconcile()
        self._write_graph_file()
        self._ensure_graph_daemon_running()
        # Both ports must appear on the K8s Service so consumers can reach
        # them via the Service VIP (otherwise the cluster IP returns 502
        # before even hitting istio). Crowsnest is workloadless but Juju
        # still manages a Service per app.
        self.unit.set_ports(self._topology.port, GRAPH_PORT)
        self._configure_ingress()
        # Re-sync both the top-level URL and the jsonData url field so the
        # plugin's proxy route renders correctly even after ingress changes.
        url = self._source_url()
        self._grafana_source._extra_fields = {"url": url}
        self._grafana_source.update_source(url)
        self._slo_load_error = None

        if not self.unit.is_leader():
            return

        catalog = self._load_slo_catalog()
        if not catalog:
            return

        try:
            self._sloth.provide_slos(catalog)
            logger.info("Published SLO catalog (%d bytes)", len(catalog))
        except Exception as e:
            self._slo_load_error = f"SLO catalog invalid: {e}"
            logger.exception("Failed to publish SLO catalog")

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        if self._slo_load_error:
            event.add_status(ops.BlockedStatus(self._slo_load_error))
        elif not self.unit.is_leader():
            event.add_status(ops.ActiveStatus("Standby (leader publishes SLOs)"))
        else:
            event.add_status(ops.ActiveStatus())


if __name__ == "__main__":
    ops.main(CharmarrCrowsnestCharm)
