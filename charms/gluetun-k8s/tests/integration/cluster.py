# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Discovery of the cluster addressing the VPN kill switch must not block.

The client init container drops its default route and keeps only
NOT_ROUTED_TO_GATEWAY_CIDRS reachable. Declaring those CIDRs as constants
assumes every cluster allocates pod addresses the same way, and CI clusters do
not: system pods that start before the CNI is installed land on containerd's
fallback bridge instead of the configured pod network. Any such range left out
leaves the container unable to resolve DNS, so it is discovered at runtime.
"""

import ipaddress
import logging
import subprocess

logger = logging.getLogger(__name__)

KUBECTL_TIMEOUT = 30
DISCOVERED_PREFIXLEN = 16


def _kubectl(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["kubectl", *args],
            capture_output=True,
            text=True,
            timeout=KUBECTL_TIMEOUT,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("kubectl %s failed: %s", " ".join(args), e)
        return None
    return result.stdout


def node_ips() -> list[str]:
    """Internal IP of every node."""
    out = _kubectl(
        [
            "get",
            "nodes",
            "-o",
            "jsonpath={.items[*].status.addresses[?(@.type=='InternalIP')].address}",
        ]
    )
    return out.split() if out else []


def pod_ips() -> list[str]:
    """IP of every pod that has one, across all namespaces."""
    out = _kubectl(["get", "pods", "-A", "-o", "jsonpath={.items[*].status.podIP}"])
    return out.split() if out else []


def _covered(ip: str, cidrs: list[str]) -> bool:
    address = ipaddress.ip_address(ip)
    return any(address in ipaddress.ip_network(cidr) for cidr in cidrs)


def discover_cluster_cidrs(declared: list[str]) -> list[str]:
    """Extend declared CIDRs with the pod networks the cluster actually uses.

    An address no declared CIDR covers is widened to a fixed prefix, since the
    allocating bridge's own range is not visible through the API. Host-network
    pods report the node address and are already covered, so they add nothing.
    """
    discovered: list[str] = []

    for ip in pod_ips():
        if _covered(ip, [*declared, *discovered]):
            continue
        network = ipaddress.ip_network(f"{ip}/{DISCOVERED_PREFIXLEN}", strict=False)
        logger.warning("pod network %s is outside the declared CIDRs, adding it", network)
        discovered.append(str(network))

    return [*declared, *discovered]
