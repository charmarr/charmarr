# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Speedtest action handler for gluetun charm.

Runs a speedtest from within the charm's network namespace, which is shared
with the gluetun container and therefore subject to VPN routing rules.
"""

import logging

import ops
import speedtest

logger = logging.getLogger(__name__)


def handle_run_speedtest(event: ops.ActionEvent, container: ops.Container) -> None:
    """Run a speedtest to measure VPN throughput and latency.

    The speedtest runs in the charm process which shares the pod network
    namespace with gluetun, so results reflect actual VPN performance.
    """
    if not container.can_connect():
        event.fail("Cannot connect to gluetun container — is gluetun running?")
        return

    logger.info("Running speedtest via VPN tunnel")
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        st.download()
        st.upload()

        results = st.results.dict()
        server = results["server"]

        event.set_results(
            {
                "download-mbps": str(round(results["download"] / 1_000_000, 2)),
                "upload-mbps": str(round(results["upload"] / 1_000_000, 2)),
                "ping-ms": str(round(results["ping"], 2)),
                "server": f"{server['sponsor']} ({server['country']})",
                "server-host": server["host"],
            }
        )
    except speedtest.ConfigRetrievalError as e:
        event.fail(f"Failed to reach speedtest.net — VPN may not be connected: {e}")
    except speedtest.NoMatchedServers:
        event.fail("No speedtest servers available")
    except speedtest.SpeedtestException as e:
        event.fail(f"Speedtest error: {e}")
    except Exception as e:
        logger.exception("Unexpected error during speedtest")
        event.fail(f"Speedtest failed: {e}")
