# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Plex server claim utilities.

Since Juju charms bypass s6-overlay and run Plex directly, the PLEX_CLAIM
environment variable is not processed. This module provides the claim
functionality that would normally be handled by the LinuxServer init scripts.
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

PLEX_CLAIM_API = "https://plex.tv/api/claim/exchange"


def extract_machine_identifier(preferences_content: str) -> str | None:
    """Extract ProcessedMachineIdentifier from Preferences.xml content."""
    match = re.search(r'ProcessedMachineIdentifier="([^"]+)"', preferences_content)
    return match.group(1) if match else None


def exchange_claim_token(claim_token: str, machine_identifier: str) -> str | None:
    """Exchange claim token for PlexOnlineToken via Plex API.

    Returns the PlexOnlineToken on success, None on failure.
    """
    try:
        response = httpx.post(
            f"{PLEX_CLAIM_API}?token={claim_token}",
            headers={
                "X-Plex-Client-Identifier": machine_identifier,
                "X-Plex-Product": "Plex Media Server",
                "X-Plex-Version": "1.1",
            },
            timeout=30.0,
        )
        response.raise_for_status()

        match = re.search(r"<authentication-token>([^<]+)</authentication-token>", response.text)
        if not match:
            logger.error("Claim response missing authentication-token: %s", response.text)
            return None

        return match.group(1)

    except httpx.HTTPStatusError as e:
        logger.error("Claim API request failed: %s", e)
        return None
    except httpx.RequestError as e:
        logger.error("Claim API connection failed: %s", e)
        return None


def inject_online_token(preferences_content: str, online_token: str) -> str:
    """Inject PlexOnlineToken into Preferences.xml content."""
    if "PlexOnlineToken" in preferences_content:
        return re.sub(
            r'PlexOnlineToken="[^"]*"',
            f'PlexOnlineToken="{online_token}"',
            preferences_content,
        )
    return preferences_content.replace("/>", f' PlexOnlineToken="{online_token}"/>')


def extract_custom_connections(preferences_content: str) -> list[str]:
    """Extract customConnections URLs from Preferences.xml content."""
    match = re.search(r'customConnections="([^"]*)"', preferences_content)
    if not match or not match.group(1):
        return []
    return [url.strip() for url in match.group(1).split(",") if url.strip()]


def ensure_custom_connection(preferences_content: str, url: str) -> str:
    """Ensure URL is present in customConnections, preserving existing URLs."""
    existing = extract_custom_connections(preferences_content)
    if url in existing:
        return preferences_content

    existing.append(url)
    new_value = ",".join(existing)

    if "customConnections=" in preferences_content:
        return re.sub(
            r'customConnections="[^"]*"',
            f'customConnections="{new_value}"',
            preferences_content,
        )
    return preferences_content.replace("/>", f' customConnections="{new_value}"/>')
