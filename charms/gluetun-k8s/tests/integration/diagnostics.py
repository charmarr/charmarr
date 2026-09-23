# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Cluster state capture for integration test triage.

CI failures here are usually environmental (CNI addressing, agent reachability)
rather than charm bugs, and the pytest assertion alone never says which. These
probes run on every session and again on failure so a single CI run carries
enough state to tell them apart.
"""

import ipaddress
import json
import logging
import subprocess

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 30
DEBUG_LOG_LINES = 300

TOPOLOGY_PROBES: tuple[tuple[str, list[str]], ...] = (
    ("nodes", ["kubectl", "get", "nodes", "-o", "wide"]),
    (
        "node-pod-cidrs",
        [
            "kubectl",
            "get",
            "nodes",
            "-o",
            "custom-columns=NAME:.metadata.name,PODCIDR:.spec.podCIDR,PODCIDRS:.spec.podCIDRs",
        ],
    ),
    ("kube-system-pods", ["kubectl", "get", "pods", "-n", "kube-system", "-o", "wide"]),
    ("all-pod-ips", ["kubectl", "get", "pods", "-A", "-o", "wide"]),
    ("cilium-endpoints", ["kubectl", "get", "ciliumendpoints", "-A"]),
)

FAILURE_PROBES: tuple[tuple[str, list[str]], ...] = (
    ("networkpolicies", ["kubectl", "get", "networkpolicies", "-A", "-o", "yaml"]),
    ("ciliumnetworkpolicies", ["kubectl", "get", "ciliumnetworkpolicies", "-A", "-o", "yaml"]),
    ("cilium-endpoints", ["kubectl", "get", "ciliumendpoints", "-A", "-o", "wide"]),
    ("events", ["kubectl", "get", "events", "-A", "--sort-by=.lastTimestamp"]),
)


def _run(name: str, cmd: list[str], tail: int | None = None) -> None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("probe %s could not run: %s", name, e)
        return

    output = result.stdout.strip() or result.stderr.strip()
    if tail:
        output = "\n".join(output.splitlines()[-tail:])
    logger.info("=== %s ===\n%s", name, output)


def _node_ips() -> list[str]:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "nodes",
                "-o",
                "jsonpath={.items[*].status.addresses[?(@.type=='InternalIP')].address}",
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return result.stdout.split()


def warn_on_cidr_overlap(pod_cidr: str, service_cidr: str) -> None:
    """Warn when a node address falls inside a CIDR the kill switch treats as pod traffic.

    The tests declare pod and service CIDRs as constants. A runner whose node
    address falls inside one of them makes node and pod traffic indistinguishable
    to the NetworkPolicy, which no local cluster reproduces.
    """
    for raw in (pod_cidr, service_cidr):
        network = ipaddress.ip_network(raw)
        for ip in _node_ips():
            if ipaddress.ip_address(ip) in network:
                logger.warning("node %s falls inside declared CIDR %s", ip, network)


def log_cluster_topology() -> None:
    """Record addressing facts that distinguish CI clusters from local ones."""
    for name, cmd in TOPOLOGY_PROBES:
        _run(name, cmd)


def _models() -> list[str]:
    """Every model except the controller's own."""
    try:
        result = subprocess.run(
            ["juju", "models", "--format=json"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            check=True,
        )
        data = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        logger.warning("could not list models: %s", e)
        return []
    names = [m.get("short-name", "") for m in data.get("models", [])]
    return [n for n in names if n and n != "controller"]


def log_failure_context(model: str | None = None) -> None:
    """Record policy and workload state after a failing test.

    The model is discovered rather than taken from the test, because a failure
    inside a fixture may leave it unresolved and these probes are worth more
    than the assertion that triggered them.
    """
    for name, cmd in FAILURE_PROBES:
        _run(name, cmd)

    for target in [model] if model else _models():
        _run(f"{target}/status", ["juju", "status", "-m", target, "--format=yaml"])
        _run(
            f"{target}/debug-log",
            ["juju", "debug-log", "-m", target, "--replay", "--no-tail", "--level", "WARNING"],
            tail=DEBUG_LOG_LINES,
        )
        _run(f"{target}/pods", ["kubectl", "get", "pods", "-n", target, "-o", "wide"])
        _run(f"{target}/configmaps", ["kubectl", "get", "configmap", "-n", target, "-o", "yaml"])
        for flag in ("--previous", "--tail=50"):
            _run(
                f"{target}/vpn-route-init {flag}",
                [
                    "kubectl",
                    "logs",
                    "-n",
                    target,
                    "charmarr-multimeter-0",
                    "-c",
                    "vpn-route-init",
                    flag,
                ],
            )
        _run(
            f"{target}/multimeter-describe",
            ["kubectl", "describe", "pod", "-n", target, "charmarr-multimeter-0"],
        )
