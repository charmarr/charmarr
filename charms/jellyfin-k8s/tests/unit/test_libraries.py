# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for Jellyfin library naming."""

import pytest

from _jellyfin import collection_type, library_name
from charmarr_lib.core import ContentVariant, MediaManager


@pytest.mark.parametrize(
    ("manager", "variant", "expected"),
    [
        (MediaManager.RADARR, ContentVariant.STANDARD, "Movies"),
        (MediaManager.RADARR, ContentVariant.UHD, "Movies (4K)"),
        (MediaManager.RADARR, ContentVariant.ANIME, "Anime Movies"),
        (MediaManager.SONARR, ContentVariant.STANDARD, "TV Shows"),
        (MediaManager.SONARR, ContentVariant.UHD, "TV Shows (4K)"),
        (MediaManager.SONARR, ContentVariant.ANIME, "Anime"),
        (MediaManager.LIDARR, ContentVariant.STANDARD, "Media"),
    ],
)
def test_library_name(manager, variant, expected):
    """Library names are distinct per manager and content variant."""
    assert library_name(manager, variant) == expected


@pytest.mark.parametrize(
    ("manager", "expected"),
    [
        (MediaManager.RADARR, "movies"),
        (MediaManager.SONARR, "tvshows"),
    ],
)
def test_collection_type(manager, expected):
    """Media managers map to Jellyfin collection types."""
    assert collection_type(manager) == expected
