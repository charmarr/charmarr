# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""LibreSpeed speedtest action handler.

Runs the bundled librespeed-cli binary inside the gluetun container so the
test traverses the VPN tunnel. The binary is pushed lazily into /tmp on first
invocation and reused until the pod is recreated.
"""

import json
import logging
import pathlib
from typing import Any

import ops
from ops.pebble import ExecError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LIBRESPEED_BINARY_SRC = pathlib.Path(__file__).parent.parent / "bin" / "librespeed-cli"
LIBRESPEED_BINARY_DEST = "/tmp/librespeed-cli"

EXEC_TIMEOUT_OVERHEAD = 30


class LibrespeedServer(BaseModel):
    """Server selected for the test."""

    name: str = ""
    url: str = ""


class LibrespeedResult(BaseModel):
    """Single librespeed-cli JSON result entry."""

    server: LibrespeedServer = Field(default_factory=LibrespeedServer)
    bytes_sent: int = 0
    bytes_received: int = 0
    ping: float = 0.0
    jitter: float = 0.0
    upload: float = 0.0
    download: float = 0.0


def _ensure_binary_pushed(container: ops.Container) -> None:
    """Push the librespeed-cli binary into the container if not already present."""
    if container.exists(LIBRESPEED_BINARY_DEST):
        return
    with LIBRESPEED_BINARY_SRC.open("rb") as f:
        container.push(LIBRESPEED_BINARY_DEST, f, permissions=0o755, make_dirs=True)
    logger.info("Pushed librespeed-cli to %s", LIBRESPEED_BINARY_DEST)


def _build_command(server_id: int | None, duration: int, timeout: int) -> list[str]:
    """Build the librespeed-cli argv. ICMP ping is disabled (unreliable on Linux)."""
    cmd = [
        LIBRESPEED_BINARY_DEST,
        "--json",
        "--no-icmp",
        "--duration",
        str(duration),
        "--timeout",
        str(timeout),
    ]
    if server_id is not None:
        cmd.extend(["--server", str(server_id)])
    return cmd


def _format_result(result: LibrespeedResult) -> dict[str, Any]:
    """Map a parsed librespeed result into action result keys."""
    return {
        "download-mbps": result.download,
        "upload-mbps": result.upload,
        "ping-ms": result.ping,
        "jitter-ms": result.jitter,
        "bytes-sent": result.bytes_sent,
        "bytes-received": result.bytes_received,
        "server-name": result.server.name,
        "server-url": result.server.url,
    }


def _parse_output(output: str) -> LibrespeedResult:
    """Parse librespeed-cli --json output (a JSON array with one entry)."""
    payload = json.loads(output)
    if not isinstance(payload, list) or not payload:
        raise ValueError("librespeed-cli returned no results")
    return LibrespeedResult.model_validate(payload[0])


def handle_speedtest(event: ops.ActionEvent, container: ops.Container) -> None:
    """Run a LibreSpeed test inside the gluetun container and set action results."""
    if not container.can_connect():
        event.fail("Cannot connect to gluetun container")
        return

    server_id = event.params.get("server-id")
    duration = int(event.params.get("duration", 15))
    timeout = int(event.params.get("timeout", 30))

    try:
        _ensure_binary_pushed(container)
    except OSError as e:
        event.fail(f"Failed to push librespeed-cli into container: {e}")
        return

    cmd = _build_command(server_id, duration, timeout)
    # Allow for two test phases (download + upload) plus startup overhead.
    exec_timeout = float(duration * 2 + timeout + EXEC_TIMEOUT_OVERHEAD)

    try:
        process = container.exec(cmd, timeout=exec_timeout)
        output, _ = process.wait_output()
    except ExecError as e:
        event.fail(f"librespeed-cli failed (exit {e.exit_code}): {e.stderr or e.stdout}")
        return
    except TimeoutError:
        event.fail(f"librespeed-cli timed out after {exec_timeout}s")
        return

    try:
        result = _parse_output(output)
    except (json.JSONDecodeError, ValueError) as e:
        event.fail(f"Failed to parse librespeed-cli output: {e}")
        return

    event.set_results(_format_result(result))
