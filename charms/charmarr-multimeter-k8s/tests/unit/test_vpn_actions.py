# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for VPN testing action handlers."""

from unittest.mock import MagicMock

import pytest
from lightkube import ApiError

from _vpn_test_actions import (
    handle_check_configmap,
    handle_check_connectivity,
    handle_check_network_policy,
    handle_check_vxlan_interface,
    handle_get_container_env,
    handle_get_external_ip,
    handle_get_statefulset_containers,
)


@pytest.fixture
def mock_event():
    event = MagicMock()
    event.params = {}
    return event


def test_get_external_ip_returns_ip(mock_event):
    container = MagicMock()
    container.can_connect.return_value = True
    container.exec.return_value.wait_output.return_value = ("185.112.34.56", None)

    handle_get_external_ip(mock_event, container)

    mock_event.set_results.assert_called_with({"ip": "185.112.34.56"})


def test_get_external_ip_fails_on_empty(mock_event):
    container = MagicMock()
    container.can_connect.return_value = True
    container.exec.return_value.wait_output.return_value = ("", None)

    handle_get_external_ip(mock_event, container)

    mock_event.fail.assert_called()


def test_check_vxlan_exists_with_ip(mock_event):
    container = MagicMock()
    container.can_connect.return_value = True
    container.exec.return_value.wait_output.return_value = (
        "4: vxlan0    inet 172.16.0.23/24 brd 172.16.0.255",
        None,
    )

    handle_check_vxlan_interface(mock_event, container)

    mock_event.set_results.assert_called_with({"exists": "true", "ip": "172.16.0.23"})


def test_check_vxlan_not_exists(mock_event):
    container = MagicMock()
    container.can_connect.return_value = True
    container.exec.return_value.wait_output.return_value = ("", None)

    handle_check_vxlan_interface(mock_event, container)

    mock_event.set_results.assert_called_with({"exists": "false", "ip": ""})


def test_get_statefulset_containers_returns_names(mock_event):
    mock_event.params = {"namespace": "ns", "name": "sts"}
    k8s = MagicMock()
    c1, c2, init = MagicMock(), MagicMock(), MagicMock()
    c1.name, c2.name, init.name = "main", "sidecar", "init"
    sts = MagicMock()
    sts.spec.template.spec.containers = [c1, c2]
    sts.spec.template.spec.initContainers = [init]
    k8s.get.return_value = sts

    handle_get_statefulset_containers(mock_event, k8s)

    mock_event.set_results.assert_called_with(
        {"containers": "main,sidecar", "init-containers": "init"}
    )


def test_check_network_policy_exists(mock_event):
    mock_event.params = {"namespace": "ns", "name": "np"}
    k8s = MagicMock()
    mock_to = MagicMock()
    mock_to.ipBlock.cidr = "10.1.0.0/16"
    np = MagicMock()
    np.spec.egress = [MagicMock(to=[mock_to])]
    k8s.get.return_value = np

    handle_check_network_policy(mock_event, k8s)

    mock_event.set_results.assert_called_with({"exists": "true", "egress-cidrs": "10.1.0.0/16"})


def test_check_network_policy_not_exists(mock_event):
    mock_event.params = {"namespace": "ns", "name": "np"}
    k8s = MagicMock()
    k8s.get.side_effect = ApiError(response=MagicMock(status_code=404))

    handle_check_network_policy(mock_event, k8s)

    mock_event.set_results.assert_called_with({"exists": "false", "egress-cidrs": ""})


def test_check_configmap_exists(mock_event):
    mock_event.params = {"namespace": "ns", "name": "cm"}
    k8s = MagicMock()
    k8s.get.return_value = MagicMock()

    handle_check_configmap(mock_event, k8s)

    mock_event.set_results.assert_called_with({"exists": "true"})


def test_check_configmap_not_exists(mock_event):
    mock_event.params = {"namespace": "ns", "name": "cm"}
    k8s = MagicMock()
    k8s.get.side_effect = ApiError(response=MagicMock(status_code=404))

    handle_check_configmap(mock_event, k8s)

    mock_event.set_results.assert_called_with({"exists": "false"})


def test_check_connectivity_reachable(mock_event):
    mock_event.params = {"target": "1.1.1.1", "timeout": 5}
    container = MagicMock()
    container.can_connect.return_value = True
    container.exec.return_value.wait_output.return_value = ("", None)

    handle_check_connectivity(mock_event, container)

    mock_event.set_results.assert_called_with({"reachable": "true"})


def test_check_connectivity_unreachable(mock_event):
    mock_event.params = {"target": "1.1.1.1", "timeout": 5}
    container = MagicMock()
    container.can_connect.return_value = True
    container.exec.return_value.wait_output.side_effect = Exception("timeout")

    handle_check_connectivity(mock_event, container)

    mock_event.set_results.assert_called_with({"reachable": "false"})


def test_get_container_env_returns_all(mock_event):
    mock_event.params = {"namespace": "ns", "name": "sts", "container": "init"}
    k8s = MagicMock()
    env1, env2 = MagicMock(), MagicMock()
    env1.name, env1.value = "VXLAN_ID", "42"
    env2.name, env2.value = "GATEWAY", "gw.svc"
    c = MagicMock()
    c.name = "init"
    c.env = [env1, env2]
    sts = MagicMock()
    sts.spec.template.spec.containers = []
    sts.spec.template.spec.initContainers = [c]
    k8s.get.return_value = sts

    handle_get_container_env(mock_event, k8s)

    mock_event.set_results.assert_called_with({"VXLAN_ID": "42", "GATEWAY": "gw.svc"})


def test_get_container_env_returns_specific_var(mock_event):
    mock_event.params = {"namespace": "ns", "name": "sts", "container": "init", "var": "VXLAN_ID"}
    k8s = MagicMock()
    env = MagicMock()
    env.name, env.value = "VXLAN_ID", "42"
    c = MagicMock()
    c.name = "init"
    c.env = [env]
    sts = MagicMock()
    sts.spec.template.spec.containers = []
    sts.spec.template.spec.initContainers = [c]
    k8s.get.return_value = sts

    handle_get_container_env(mock_event, k8s)

    mock_event.set_results.assert_called_with({"value": "42"})
