# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helpers for reading and patching Jellyfin's system.xml."""

import re

_METRICS_RE = re.compile(r"<EnableMetrics>\s*(true|false)\s*</EnableMetrics>", re.IGNORECASE)
_WIZARD_RE = re.compile(
    r"<IsStartupWizardCompleted>\s*true\s*</IsStartupWizardCompleted>", re.IGNORECASE
)
_ROOT_OPEN_RE = re.compile(r"(<ServerConfiguration\b[^>]*>)")


def enable_metrics(content: str) -> str:
    """Return system.xml content with the native metrics endpoint enabled.

    Jellyfin seeds ``<EnableMetrics>false</EnableMetrics>`` on first run. Flip
    it to true; if the element is absent, insert it after the root element.
    """
    if _METRICS_RE.search(content):
        return _METRICS_RE.sub("<EnableMetrics>true</EnableMetrics>", content)

    def _insert(match: re.Match[str]) -> str:
        return f"{match.group(1)}\n  <EnableMetrics>true</EnableMetrics>"

    return _ROOT_OPEN_RE.sub(_insert, content, count=1)


def is_startup_wizard_completed(content: str) -> bool:
    """Return True when system.xml marks the startup wizard as completed."""
    return bool(_WIZARD_RE.search(content))
