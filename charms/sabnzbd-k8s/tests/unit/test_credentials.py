# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for SABnzbd credentials module."""

from _sabnzbd._credentials import build_sabnzbd_config, reconcile_sabnzbd_config


class TestReconcileSabnzbdConfig:
    """Tests for reconcile_sabnzbd_config function."""

    def test_preserves_usenet_server_settings(self):
        """Regression test: Usenet server host/port must not be overwritten."""
        content = """\
[misc]
api_key = old-key
host = 0.0.0.0
port = 8080

[servers]
    [[usenet-provider]]
    host = news.usenetprovider.com
    port = 563
    username = myuser
    password = mypass
    ssl = 1
"""
        result = reconcile_sabnzbd_config(content, api_key="new-key", app_name="sabnzbd-k8s")

        assert "api_key = new-key" in result
        assert "host = news.usenetprovider.com" in result
        assert "port = 563" in result
        assert "username = myuser" in result
        assert "password = mypass" in result

    def test_builds_fresh_config_when_none(self):
        """Fresh config is built when content is None."""
        result = reconcile_sabnzbd_config(None, api_key="test-key", app_name="sabnzbd-k8s")

        assert "api_key = test-key" in result
        assert "host = 0.0.0.0" in result
        assert "sabnzbd-k8s, localhost" in result


class TestBuildSabnzbdConfig:
    """Tests for build_sabnzbd_config function."""

    def test_includes_required_fields(self):
        """Config includes all required fields."""
        result = build_sabnzbd_config("my-api-key", "my-app")

        assert "api_key = my-api-key" in result
        assert "host = 0.0.0.0" in result
        assert "port = 8080" in result
        assert "my-app, localhost" in result

    def test_includes_url_base_when_provided(self):
        """URL base is included when provided."""
        result = build_sabnzbd_config("key", "app", url_base="/sabnzbd")

        assert "url_base = /sabnzbd" in result

    def test_excludes_url_base_when_none(self):
        """URL base line is excluded when None."""
        result = build_sabnzbd_config("key", "app", url_base=None)

        assert "url_base" not in result
