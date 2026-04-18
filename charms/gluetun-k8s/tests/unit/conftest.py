# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for unit tests."""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Context

# Mock the speedtest module (speedtest-cli) which is a runtime-only dependency
# not available in the unit test environment.
_mock_speedtest = ModuleType("speedtest")
_mock_speedtest.Speedtest = type("Speedtest", (), {})  # type: ignore[attr-defined]
_mock_speedtest.ConfigRetrievalError = type("ConfigRetrievalError", (Exception,), {})  # type: ignore[attr-defined]
_mock_speedtest.NoMatchedServers = type("NoMatchedServers", (Exception,), {})  # type: ignore[attr-defined]
_mock_speedtest.SpeedtestException = type("SpeedtestException", (Exception,), {})  # type: ignore[attr-defined]
sys.modules["speedtest"] = _mock_speedtest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from charm import GluetunCharm


@pytest.fixture
def ctx() -> Context[GluetunCharm]:
    """Create a testing context for GluetunCharm."""
    return Context(GluetunCharm)


@pytest.fixture
def mock_k8s():
    """Create a mock K8sResourceManager and get_cluster_dns_ip."""
    with (
        patch("charm.K8sResourceManager") as mock_class,
        patch("charm.get_cluster_dns_ip", return_value="10.152.183.10"),
    ):
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


def make_privileged_statefulset() -> MagicMock:
    """Create a mock StatefulSet with privileged gluetun container."""
    mock_sts = MagicMock()
    mock_container = MagicMock()
    mock_container.name = "gluetun"
    mock_container.securityContext.privileged = True
    mock_sts.spec.template.spec.containers = [mock_container]
    return mock_sts


@pytest.fixture
def mock_k8s_privileged():
    """Create a mock K8sResourceManager with privileged StatefulSet and mocked VPN health."""
    with (
        patch("charm.K8sResourceManager") as mock_class,
        patch("charm.get_cluster_dns_ip", return_value="10.152.183.10"),
        patch("charm.GluetunCharm._fetch_public_ip", return_value="1.2.3.4"),
    ):
        mock_instance = MagicMock()
        mock_instance.get.return_value = make_privileged_statefulset()
        mock_class.return_value = mock_instance
        yield mock_instance
