# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""VPN-related step definitions for gluetun-k8s integration tests."""

import subprocess

import jubilant
from pytest_bdd import when

from charmarr_lib.testing import wait_for_active_idle


@when("the gluetun container is stopped")
def stop_gluetun_container(juju: jubilant.Juju) -> None:
    """Stop the gluetun container by deleting the pod (simulates VPN failure)."""
    namespace = juju.model
    subprocess.run(
        ["kubectl", "delete", "pod", "gluetun-0", "-n", namespace, "--grace-period=0", "--force"],
        check=True,
        capture_output=True,
    )


@when("the gluetun container is restarted")
def restart_gluetun_container(juju: jubilant.Juju) -> None:
    """Restart gluetun by deleting pod and waiting for it to come back."""
    namespace = juju.model
    subprocess.run(
        ["kubectl", "delete", "pod", "gluetun-0", "-n", namespace, "--grace-period=0", "--force"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "kubectl",
            "wait",
            "--for=condition=ready",
            "pod/gluetun-0",
            "-n",
            namespace,
            "--timeout=300s",
        ],
        check=True,
        capture_output=True,
    )
    wait_for_active_idle(juju)
