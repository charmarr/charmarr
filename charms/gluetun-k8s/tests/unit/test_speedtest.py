# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for the run-speedtest action handler."""

import json
from unittest.mock import MagicMock, patch

import pytest
from ops.pebble import ExecError

from _speedtest import (
    LIBRESPEED_BINARY_DEST,
    _build_command,
    _parse_output,
    handle_speedtest,
)

SAMPLE_JSON = json.dumps(
    [
        {
            "timestamp": "2026-04-27T19:02:59.554331101+02:00",
            "server": {
                "name": "Amsterdam, Netherlands (Clouvider)",
                "url": "https://ams.speedtest.clouvider.net/backend",
            },
            "client": {"ip": "1.2.3.4"},
            "bytes_sent": 35061760,
            "bytes_received": 345601560,
            "ping": 22.36,
            "jitter": 1.49,
            "upload": 50.07,
            "download": 493.45,
            "share": "",
        }
    ]
)


@pytest.fixture
def event():
    """Action event with default speedtest params."""
    e = MagicMock()
    e.params = {"duration": 15, "timeout": 30}
    return e


@pytest.fixture
def container():
    """Pebble container that can connect, with binary already present."""
    c = MagicMock()
    c.can_connect.return_value = True
    c.exists.return_value = True
    return c


def _exec_returning(output: str) -> MagicMock:
    """Build a MagicMock for container.exec(...) that yields `output` on wait_output()."""
    process = MagicMock()
    process.wait_output.return_value = (output, "")
    return process


def test_happy_path_maps_all_result_fields(event, container):
    container.exec.return_value = _exec_returning(SAMPLE_JSON)

    handle_speedtest(event, container)

    event.set_results.assert_called_once_with(
        {
            "download-mbps": 493.45,
            "upload-mbps": 50.07,
            "ping-ms": 22.36,
            "jitter-ms": 1.49,
            "bytes-sent": 35061760,
            "bytes-received": 345601560,
            "server-name": "Amsterdam, Netherlands (Clouvider)",
            "server-url": "https://ams.speedtest.clouvider.net/backend",
        }
    )
    event.fail.assert_not_called()


def test_fails_when_container_unreachable(event):
    container = MagicMock()
    container.can_connect.return_value = False

    handle_speedtest(event, container)

    event.fail.assert_called_once()
    container.exec.assert_not_called()


def test_pushes_binary_when_missing(event, container):
    container.exists.return_value = False
    container.exec.return_value = _exec_returning(SAMPLE_JSON)

    with patch("_speedtest.LIBRESPEED_BINARY_SRC") as src:
        src.open.return_value.__enter__.return_value = b"binary-bytes"
        handle_speedtest(event, container)

    container.push.assert_called_once()
    args, kwargs = container.push.call_args
    assert args[0] == LIBRESPEED_BINARY_DEST
    assert kwargs["permissions"] == 0o755


def test_skips_push_when_binary_present(event, container):
    container.exec.return_value = _exec_returning(SAMPLE_JSON)

    handle_speedtest(event, container)

    container.push.assert_not_called()


def test_fails_on_exec_error(event, container):
    container.exec.return_value.wait_output.side_effect = ExecError(
        command=[LIBRESPEED_BINARY_DEST], exit_code=1, stdout="", stderr="connection refused"
    )

    handle_speedtest(event, container)

    event.fail.assert_called_once()
    assert "connection refused" in event.fail.call_args.args[0]
    event.set_results.assert_not_called()


def test_fails_on_exec_timeout(event, container):
    container.exec.return_value.wait_output.side_effect = TimeoutError()

    handle_speedtest(event, container)

    event.fail.assert_called_once()
    assert "timed out" in event.fail.call_args.args[0]


def test_fails_on_malformed_json(event, container):
    container.exec.return_value = _exec_returning("not-json")

    handle_speedtest(event, container)

    event.fail.assert_called_once()
    event.set_results.assert_not_called()


def test_fails_on_empty_json_array(event, container):
    container.exec.return_value = _exec_returning("[]")

    handle_speedtest(event, container)

    event.fail.assert_called_once()


def test_command_includes_server_id_when_provided():
    cmd = _build_command(server_id=42, duration=10, timeout=20)
    assert "--server" in cmd
    assert "42" in cmd
    assert cmd[cmd.index("--server") + 1] == "42"
    assert "--duration" in cmd and cmd[cmd.index("--duration") + 1] == "10"


def test_command_omits_server_id_when_absent():
    cmd = _build_command(server_id=None, duration=15, timeout=30)
    assert "--server" not in cmd
    assert "--no-icmp" in cmd
    assert "--json" in cmd


def test_parse_output_rejects_non_list():
    with pytest.raises(ValueError):
        _parse_output("{}")
