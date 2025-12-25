# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""VPN integration testing action handlers.

Each function handles an action event, performing the operation and
setting results or failing the action as appropriate.
"""

import ops
from lightkube import ApiError
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import ConfigMap
from lightkube.resources.networking_v1 import NetworkPolicy

from charmarr_lib.core import K8sResourceManager


def handle_get_external_ip(event: ops.ActionEvent, container) -> None:
    """Get external IP from within the container."""
    if not container.can_connect():
        event.fail("Cannot connect to container")
        return
    try:
        process = container.exec(["wget", "-qO-", "https://ifconfig.me/ip", "--timeout=10"])
        output, _ = process.wait_output()
        ip = output.strip()
        if ip:
            event.set_results({"ip": ip})
        else:
            event.fail("Empty response from ifconfig.me")
    except Exception as e:
        event.fail(f"Failed to get external IP: {e}")


def handle_check_vxlan_interface(event: ops.ActionEvent, container) -> None:
    """Check if vxlan interface exists and get its IP."""
    if not container.can_connect():
        event.fail("Cannot connect to container")
        return
    try:
        process = container.exec(["ip", "-o", "addr", "show", "vxlan0"])
        output, _ = process.wait_output()
        if output.strip():
            ip = None
            parts = output.split()
            for i, part in enumerate(parts):
                if part == "inet" and i + 1 < len(parts):
                    ip = parts[i + 1].split("/")[0]
                    break
            event.set_results({"exists": "true", "ip": ip or ""})
        else:
            event.set_results({"exists": "false", "ip": ""})
    except Exception:
        event.set_results({"exists": "false", "ip": ""})


def handle_check_connectivity(event: ops.ActionEvent, container) -> None:
    """Check if container can reach a target."""
    if not container.can_connect():
        event.fail("Cannot connect to container")
        return
    target = event.params["target"]
    timeout = event.params.get("timeout", 5)
    try:
        process = container.exec(
            ["wget", "-q", "-O", "/dev/null", f"--timeout={timeout}", f"http://{target}"]
        )
        process.wait_output()
        event.set_results({"reachable": "true"})
    except Exception:
        event.set_results({"reachable": "false"})


def handle_get_statefulset_containers(event: ops.ActionEvent, k8s: K8sResourceManager) -> None:
    """Get container names from a StatefulSet."""
    namespace = event.params["namespace"]
    name = event.params["name"]
    try:
        sts = k8s.get(StatefulSet, name, namespace)
        containers = []
        init_containers = []
        if sts.spec and sts.spec.template.spec:
            if sts.spec.template.spec.containers:
                containers = [c.name for c in sts.spec.template.spec.containers]
            if sts.spec.template.spec.initContainers:
                init_containers = [c.name for c in sts.spec.template.spec.initContainers]
        event.set_results(
            {
                "containers": ",".join(containers),
                "init-containers": ",".join(init_containers),
            }
        )
    except ApiError as e:
        event.fail(f"Failed to get StatefulSet: {e}")


def handle_get_container_env(event: ops.ActionEvent, k8s: K8sResourceManager) -> None:
    """Get environment variables from a container."""
    namespace = event.params["namespace"]
    name = event.params["name"]
    container_name = event.params["container"]
    var_name = event.params.get("var")
    try:
        sts = k8s.get(StatefulSet, name, namespace)
        env: dict[str, str] = {}
        if sts.spec and sts.spec.template.spec:
            all_containers = list(sts.spec.template.spec.containers or [])
            all_containers.extend(list(sts.spec.template.spec.initContainers or []))
            for c in all_containers:
                if c.name == container_name and c.env:
                    env = {e.name: (e.value or "") for e in c.env if e.name}
                    break
        if var_name:
            event.set_results({"value": env.get(var_name, "")})
        else:
            event.set_results(env)
    except ApiError as e:
        event.fail(f"Failed to get container env: {e}")


def handle_check_network_policy(event: ops.ActionEvent, k8s: K8sResourceManager) -> None:
    """Check if a NetworkPolicy exists and get its egress CIDRs."""
    namespace = event.params["namespace"]
    name = event.params["name"]
    try:
        np = k8s.get(NetworkPolicy, name, namespace)
        cidrs = []
        if np.spec and np.spec.egress:
            for rule in np.spec.egress:
                if rule.to:
                    for to in rule.to:
                        if to.ipBlock and to.ipBlock.cidr:
                            cidrs.append(to.ipBlock.cidr)
        event.set_results({"exists": "true", "egress-cidrs": ",".join(cidrs)})
    except ApiError:
        event.set_results({"exists": "false", "egress-cidrs": ""})


def handle_check_configmap(event: ops.ActionEvent, k8s: K8sResourceManager) -> None:
    """Check if a ConfigMap exists."""
    namespace = event.params["namespace"]
    name = event.params["name"]
    try:
        k8s.get(ConfigMap, name, namespace)
        event.set_results({"exists": "true"})
    except ApiError:
        event.set_results({"exists": "false"})
