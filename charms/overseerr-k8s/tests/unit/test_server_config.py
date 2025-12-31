# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for server configuration building."""

from ops.testing import Container, State


def test_parse_http_url(ctx):
    """Parse HTTP URL correctly."""
    container = Container(name="overseerr", can_connect=False)
    state = State(leader=True, containers=[container])
    with ctx(ctx.on.config_changed(), state) as mgr:
        hostname, port, use_ssl = mgr.charm._parse_url("http://radarr.local:7878")
    assert hostname == "radarr.local"
    assert port == 7878
    assert use_ssl is False


def test_parse_https_url(ctx):
    """Parse HTTPS URL correctly."""
    container = Container(name="overseerr", can_connect=False)
    state = State(leader=True, containers=[container])
    with ctx(ctx.on.config_changed(), state) as mgr:
        hostname, port, use_ssl = mgr.charm._parse_url("https://radarr.example.com:443/api")
    assert hostname == "radarr.example.com"
    assert port == 443
    assert use_ssl is True


def test_parse_url_default_http_port(ctx):
    """Default to port 80 for HTTP without explicit port."""
    container = Container(name="overseerr", can_connect=False)
    state = State(leader=True, containers=[container])
    with ctx(ctx.on.config_changed(), state) as mgr:
        hostname, port, use_ssl = mgr.charm._parse_url("http://radarr.local")
    assert hostname == "radarr.local"
    assert port == 80
    assert use_ssl is False


def test_parse_url_default_https_port(ctx):
    """Default to port 443 for HTTPS without explicit port."""
    container = Container(name="overseerr", can_connect=False)
    state = State(leader=True, containers=[container])
    with ctx(ctx.on.config_changed(), state) as mgr:
        hostname, port, use_ssl = mgr.charm._parse_url("https://radarr.local")
    assert hostname == "radarr.local"
    assert port == 443
    assert use_ssl is True
