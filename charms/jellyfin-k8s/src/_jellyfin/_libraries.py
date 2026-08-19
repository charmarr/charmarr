# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Mapping from media manager relation data to Jellyfin library definitions."""

from charmarr_lib.core import ContentVariant, MediaManager

_BASE_NAMES = {
    MediaManager.RADARR: "Movies",
    MediaManager.SONARR: "TV Shows",
}

_COLLECTION_TYPES = {
    MediaManager.RADARR: "movies",
    MediaManager.SONARR: "tvshows",
}


def library_name(manager: MediaManager, variant: ContentVariant) -> str:
    """Build the Jellyfin library name for a media manager instance."""
    base = _BASE_NAMES.get(manager, "Media")

    if variant == ContentVariant.UHD:
        return f"{base} (4K)"
    if variant == ContentVariant.ANIME:
        return "Anime" if manager == MediaManager.SONARR else "Anime Movies"
    return base


def collection_type(manager: MediaManager) -> str:
    """Map a media manager to its Jellyfin collection type."""
    return _COLLECTION_TYPES.get(manager, "movies")
