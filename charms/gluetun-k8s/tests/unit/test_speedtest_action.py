# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for the speedtest action handler."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import speedtest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from _speedtest_action import handle_run_speedtest


@pytest.fixture
def event():
    e = MagicMock()
    e.params = {}
    return e


@pytest.fixture
def container():
    c = MagicMock()
    c.can_connect.return_value = True
    return c


def _make_speedtest_results(download=50_000_000.0, upload=20_000_000.0, ping=12.5):
    results = MagicMock()
    results.dict.return_value = {
        "download": download,
        "upload": upload,
        "ping": ping,
        "server": {
            "sponsor": "Acme ISP",
            "country": "Netherlands",
            "host": "speedtest.acme.nl:8080",
        },
    }
    return results


def test_run_speedtest_returns_results(event, container):
    with patch("_speedtest_action.speedtest.Speedtest") as mock_st_class:
        st = MagicMock()
        st.results = _make_speedtest_results()
        mock_st_class.return_value = st

        handle_run_speedtest(event, container)

        st.get_best_server.assert_called_once()
        st.download.assert_called_once()
        st.upload.assert_called_once()
        event.set_results.assert_called_once_with(
            {
                "download-mbps": "50.0",
                "upload-mbps": "20.0",
                "ping-ms": "12.5",
                "server": "Acme ISP (Netherlands)",
                "server-host": "speedtest.acme.nl:8080",
            }
        )


def test_run_speedtest_rounds_values(event, container):
    with patch("_speedtest_action.speedtest.Speedtest") as mock_st_class:
        st = MagicMock()
        st.results = _make_speedtest_results(
            download=47_238_192.0, upload=18_991_003.0, ping=8.333
        )
        mock_st_class.return_value = st

        handle_run_speedtest(event, container)

        call_kwargs = event.set_results.call_args[0][0]
        assert call_kwargs["download-mbps"] == "47.24"
        assert call_kwargs["upload-mbps"] == "18.99"
        assert call_kwargs["ping-ms"] == "8.33"


def test_run_speedtest_fails_when_container_not_connected(event, container):
    container.can_connect.return_value = False

    handle_run_speedtest(event, container)

    event.fail.assert_called_once()
    event.set_results.assert_not_called()


def test_run_speedtest_fails_on_config_retrieval_error(event, container):
    with patch("_speedtest_action.speedtest.Speedtest") as mock_st_class:
        mock_st_class.side_effect = speedtest.ConfigRetrievalError("network error")

        handle_run_speedtest(event, container)

        event.fail.assert_called_once()
        assert "VPN may not be connected" in event.fail.call_args[0][0]


def test_run_speedtest_fails_on_no_matched_servers(event, container):
    with patch("_speedtest_action.speedtest.Speedtest") as mock_st_class:
        st = MagicMock()
        st.get_best_server.side_effect = speedtest.NoMatchedServers()
        mock_st_class.return_value = st

        handle_run_speedtest(event, container)

        event.fail.assert_called_once()
        assert "No speedtest servers" in event.fail.call_args[0][0]


def test_run_speedtest_fails_on_generic_speedtest_exception(event, container):
    with patch("_speedtest_action.speedtest.Speedtest") as mock_st_class:
        st = MagicMock()
        st.download.side_effect = speedtest.SpeedtestException("something broke")
        mock_st_class.return_value = st

        handle_run_speedtest(event, container)

        event.fail.assert_called_once()
        assert "something broke" in event.fail.call_args[0][0]


def test_run_speedtest_fails_on_unexpected_exception(event, container):
    with patch("_speedtest_action.speedtest.Speedtest") as mock_st_class:
        st = MagicMock()
        st.download.side_effect = RuntimeError("unexpected")
        mock_st_class.return_value = st

        handle_run_speedtest(event, container)

        event.fail.assert_called_once()
        assert "unexpected" in event.fail.call_args[0][0]
