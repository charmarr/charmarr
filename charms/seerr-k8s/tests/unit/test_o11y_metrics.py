# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for the Seerr o11y metric callback."""

from unittest.mock import MagicMock, patch

from ops.testing import Container, Exec, State

SEERR_CONTAINER = Container(
    name="seerr",
    can_connect=True,
    execs={
        Exec(["chown", "-R", "1000:1000", "/app/config"]),
    },
)


def test_returns_empty_when_no_api_key(ctx):
    state = State(leader=True, containers=[SEERR_CONTAINER])
    with ctx(ctx.on.update_status(), state) as mgr:
        with patch.object(mgr.charm, "_get_api_key", return_value=None):
            families = mgr.charm._build_request_gauges()
        mgr.run()

    assert families == []


def test_emits_one_family_per_request_status(ctx):
    state = State(leader=True, containers=[SEERR_CONTAINER])
    api = MagicMock()
    api.get_request_counts.return_value = {
        "pending": 2,
        "approved": 5,
        "available": 18,
        "declined": 1,
    }
    api_ctx = MagicMock()
    api_ctx.__enter__.return_value = api
    api_ctx.__exit__.return_value = None

    with ctx(ctx.on.update_status(), state) as mgr:
        with (
            patch.object(mgr.charm, "_get_api_key", return_value="sentinel-key"),
            patch.object(mgr.charm, "_get_api_client", return_value=api_ctx),
        ):
            families = mgr.charm._build_request_gauges()
        mgr.run()

    assert len(families) == 1
    family = families[0]
    assert family.name == "charmarr_requests_total"
    by_status = {s.labels["status"]: s.value for s in family.samples}
    assert by_status == {"pending": 2.0, "approved": 5.0, "available": 18.0, "declined": 1.0}


def test_returns_empty_when_api_returns_no_numeric_counts(ctx):
    state = State(leader=True, containers=[SEERR_CONTAINER])
    api = MagicMock()
    api.get_request_counts.return_value = {"meta": "not a count"}
    api_ctx = MagicMock()
    api_ctx.__enter__.return_value = api
    api_ctx.__exit__.return_value = None

    with ctx(ctx.on.update_status(), state) as mgr:
        with (
            patch.object(mgr.charm, "_get_api_key", return_value="sentinel-key"),
            patch.object(mgr.charm, "_get_api_client", return_value=api_ctx),
        ):
            families = mgr.charm._build_request_gauges()
        mgr.run()

    assert families == []
