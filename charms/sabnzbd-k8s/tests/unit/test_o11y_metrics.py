# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for the SABnzbd o11y metric callback."""

from ops.testing import Container, State

_CONTAINERS = [
    Container(name="sabnzbd", can_connect=True),
    Container(name="sabnzbd-exporter", can_connect=True),
]


def test_unsafe_mode_disabled_by_default(ctx, mock_k8s):
    state = State(leader=True, containers=_CONTAINERS)
    with ctx(ctx.on.update_status(), state) as mgr:
        families = mgr.charm._build_charm_gauges()
        mgr.run()

    assert len(families) == 1
    family = families[0]
    assert family.name == "charmarr_unsafe_mode_enabled"
    assert family.samples[0].value == 0.0


def test_unsafe_mode_enabled_when_configured(ctx, mock_k8s):
    state = State(leader=True, containers=_CONTAINERS, config={"unsafe-mode": True})
    with ctx(ctx.on.update_status(), state) as mgr:
        families = mgr.charm._build_charm_gauges()
        mgr.run()

    assert families[0].samples[0].value == 1.0
