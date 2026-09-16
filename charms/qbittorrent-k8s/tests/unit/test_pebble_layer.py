# Copyright 2026 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for add_layer_if_changed."""

from unittest.mock import MagicMock

import ops

from charm import add_layer_if_changed

LAYER: ops.pebble.LayerDict = {
    "services": {
        "workload": {
            "override": "replace",
            "command": "/bin/workload",
            "startup": "enabled",
            "user-id": 1000,
            "environment": {"TZ": "Etc/UTC"},
        }
    },
    "checks": {
        "workload-ready": {
            "override": "replace",
            "level": "ready",
            "http": {"url": "http://localhost:8080/ping"},
            "period": "10s",
            "timeout": "3s",
            "threshold": 3,
        }
    },
}


def _container(plan: ops.pebble.PlanDict) -> MagicMock:
    container = MagicMock(spec=ops.Container)
    container.get_plan.return_value = ops.pebble.Plan(plan)
    return container


def test_skips_add_layer_when_plan_already_matches():
    """Re-adding an identical layer would make Pebble re-send buffered logs."""
    container = _container({**LAYER, "log-targets": {"loki/0": {"override": "replace"}}})

    add_layer_if_changed(container, "workload", LAYER)

    container.add_layer.assert_not_called()


def test_adds_layer_when_plan_is_empty():
    container = _container({})

    add_layer_if_changed(container, "workload", LAYER)

    container.add_layer.assert_called_once()
    label, layer = container.add_layer.call_args.args
    assert label == "workload"
    assert layer.to_dict() == LAYER
    assert container.add_layer.call_args.kwargs == {"combine": True}


def test_adds_layer_when_service_changed():
    plan = ops.pebble.Layer(LAYER).to_dict()
    plan["services"]["workload"]["environment"] = {"TZ": "Europe/Athens"}
    container = _container(plan)

    add_layer_if_changed(container, "workload", LAYER)

    container.add_layer.assert_called_once()


def test_adds_layer_when_check_changed():
    plan = ops.pebble.Layer(LAYER).to_dict()
    plan["checks"]["workload-ready"]["http"] = {"url": "http://localhost:8080/base/ping"}
    container = _container(plan)

    add_layer_if_changed(container, "workload", LAYER)

    container.add_layer.assert_called_once()
