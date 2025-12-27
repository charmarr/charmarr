# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd API key generation utilities."""

import secrets

from _sabnzbd._constants import API_KEY_BYTES


def generate_api_key(length: int = API_KEY_BYTES) -> str:
    """Generate a cryptographically secure 32-character hex API key."""
    return secrets.token_hex(length)


def build_sabnzbd_config(api_key: str, app_name: str = "sabnzbd-k8s") -> str:
    """Build minimal sabnzbd.ini with API key and host/port settings."""
    return f"""[misc]
api_key = {api_key}
host = 0.0.0.0
port = 8080
host_whitelist = {app_name}, localhost
"""
