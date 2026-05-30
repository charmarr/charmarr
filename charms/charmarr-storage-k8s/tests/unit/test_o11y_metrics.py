# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for the storage o11y metric callback."""

from conftest import make_api_error_404, make_pvc
from ops.testing import Relation, State


def _gauges_by_name(families):
    return {f.name: f for f in families}


def test_gauges_when_no_pvc(ctx, mock_k8s):
    """No PVC exists yet: 3 gauges, no capacity series."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = State(
        leader=True,
        config={"backend-type": "storage-class", "storage-class": "local-path"},
    )
    with ctx(ctx.on.update_status(), state) as mgr:
        families = mgr.charm._build_storage_gauges()
        mgr.run()

    by_name = _gauges_by_name(families)
    assert set(by_name) == {
        "charmarr_storage_consumers_total",
        "charmarr_storage_pvc_bound",
        "charmarr_storage_permission_check_ok",
    }
    assert by_name["charmarr_storage_pvc_bound"].samples[0].value == 0.0
    assert by_name["charmarr_storage_pvc_bound"].samples[0].labels["backend"] == "storage-class"


def test_gauges_when_pvc_bound(ctx, mock_k8s):
    """Bound PVC: 4 gauges including capacity parsed from spec."""
    mock_k8s._custom_get_return = make_pvc(phase="Bound", size="250Gi")

    state = State(
        leader=True,
        config={"backend-type": "storage-class", "storage-class": "local-path"},
    )
    with ctx(ctx.on.update_status(), state) as mgr:
        families = mgr.charm._build_storage_gauges()
        mgr.run()

    by_name = _gauges_by_name(families)
    assert "charmarr_storage_pvc_capacity_bytes" in by_name
    assert by_name["charmarr_storage_pvc_bound"].samples[0].value == 1.0
    assert by_name["charmarr_storage_pvc_capacity_bytes"].samples[0].value == float(250 * 1024**3)
    assert (
        by_name["charmarr_storage_pvc_capacity_bytes"].samples[0].labels["backend"]
        == "storage-class"
    )


def test_consumers_total_reflects_relation_count(ctx, mock_k8s):
    """consumers_total counts bound media-storage relations."""
    mock_k8s.get.side_effect = make_api_error_404()

    state = State(
        leader=True,
        config={"backend-type": "storage-class", "storage-class": "local-path"},
        relations=[
            Relation(
                endpoint="media-storage", interface="media-storage", remote_app_name="radarr"
            ),
            Relation(
                endpoint="media-storage", interface="media-storage", remote_app_name="sonarr"
            ),
            Relation(
                endpoint="media-storage", interface="media-storage", remote_app_name="qbittorrent"
            ),
        ],
    )
    with ctx(ctx.on.update_status(), state) as mgr:
        families = mgr.charm._build_storage_gauges()
        mgr.run()

    by_name = _gauges_by_name(families)
    assert by_name["charmarr_storage_consumers_total"].samples[0].value == 3


def test_permission_check_states(ctx, mock_k8s):
    """permission_check_ok reports 1 (passed), 0 (failed), -1 (pending)."""
    mock_k8s.get.side_effect = make_api_error_404()
    state = State(
        leader=True,
        config={"backend-type": "storage-class", "storage-class": "local-path"},
    )

    with ctx(ctx.on.update_status(), state) as mgr:
        # Healthy default
        assert mgr.charm._build_storage_gauges()[2].samples[0].value == 1.0

        mgr.charm._permission_check_pending = True
        assert mgr.charm._build_storage_gauges()[2].samples[0].value == -1.0

        mgr.charm._permission_check_pending = False
        mgr.charm._permission_error = "UID mismatch on /data"
        assert mgr.charm._build_storage_gauges()[2].samples[0].value == 0.0
        mgr.run()
