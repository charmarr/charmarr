# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for charmarr-crowsnest-k8s."""

from unittest.mock import MagicMock

import httpx
import ops
from ops.testing import Relation, State

from charmarr_lib.core.interfaces import CrowsnestProviderData

_SAMPLE_METRICS = """\
# HELP charmarr_relation_bound x
# TYPE charmarr_relation_bound gauge
charmarr_relation_bound{relation="download-client",role="requires",required="true"} 1
charmarr_relation_bound{relation="vpn-gateway",role="requires",required="false"} 0
# HELP charmarr_relation_edge x
# TYPE charmarr_relation_edge gauge
charmarr_relation_edge{relation="download-client",from_app="radarr",to_app="qbittorrent"} 1
charmarr_relation_edge{relation="media-storage",from_app="radarr",to_app="storage"} 1
"""


def test_active_after_reconcile(ctx):
    """A clean reconcile lands the charm in Active state."""
    state = ctx.run(ctx.on.update_status(), State(leader=True))
    assert state.unit_status == ops.ActiveStatus()


def test_non_leader_is_standby(ctx):
    """Non-leader unit reports standby and does not attempt to publish."""
    state = ctx.run(ctx.on.update_status(), State(leader=False))
    assert state.unit_status == ops.ActiveStatus("Standby (leader publishes SLOs)")


def test_slo_catalog_loads_all_yaml_files(ctx):
    """All shipped SLO YAMLs concatenate cleanly into one multi-doc payload."""
    with ctx(ctx.on.update_status(), State(leader=True)) as mgr:
        catalog = mgr.charm._load_slo_catalog()
        mgr.run()

    assert catalog is not None
    # All four service domains present.
    assert "service: charmarr-availability" in catalog
    assert "service: charmarr-vpn" in catalog
    assert "service: charmarr-downloads" in catalog
    assert "service: charmarr-fulfillment" in catalog
    # Document separator between files.
    assert catalog.count("\n---\n") >= 3


def _fleet_relation(app: str) -> Relation:
    return Relation(
        endpoint="crowsnest",
        interface="crowsnest",
        remote_app_name=app,
        remote_app_data={
            "config": CrowsnestProviderData(
                topology_url=f"http://{app}.charmarr.svc.cluster.local:9099/metrics"
            ).model_dump_json()
        },
    )


def test_aggregate_graph_builds_nodes_and_edges(ctx, monkeypatch):
    """Successful polls of related members translate into nodes + edges."""
    response = MagicMock(spec=httpx.Response, text=_SAMPLE_METRICS)
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = MagicMock(return_value=response)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("charm.httpx.Client", MagicMock(return_value=client))

    relations = [_fleet_relation(app) for app in ("radarr", "qbittorrent", "storage")]
    with ctx(ctx.on.update_status(), State(leader=True, relations=relations)) as mgr:
        graph = mgr.charm._build_aggregate_graph()
        mgr.run()

    edge_keys = {(e["source"], e["mainstat"], e["target"]) for e in graph["edges"]}
    assert ("radarr", "download-client", "qbittorrent") in edge_keys
    assert ("radarr", "media-storage", "storage") in edge_keys

    node_ids = {n["id"] for n in graph["nodes"]}
    assert {"radarr", "qbittorrent", "storage"}.issubset(node_ids)


def test_aggregate_graph_handles_unreachable_pods(ctx, monkeypatch):
    """When every poll fails, the result is an empty graph - not a crash."""
    client = MagicMock()
    client.get = MagicMock(side_effect=httpx.ConnectError("no route"))
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("charm.httpx.Client", MagicMock(return_value=client))

    relations = [_fleet_relation(app) for app in ("radarr", "qbittorrent")]
    with ctx(ctx.on.update_status(), State(leader=True, relations=relations)) as mgr:
        graph = mgr.charm._build_aggregate_graph()
        mgr.run()

    assert graph == {"nodes": [], "edges": []}


def test_aggregate_graph_empty_without_fleet_members(ctx):
    """No related members -> empty graph, no polling attempted."""
    with ctx(ctx.on.update_status(), State(leader=True)) as mgr:
        graph = mgr.charm._build_aggregate_graph()
        mgr.run()

    assert graph == {"nodes": [], "edges": []}
