# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

# NOTE: Overseerr requires Plex OAuth to complete setup before most features
# can be tested. Currently there is no way to mock Plex authentication in
# integration tests, so we can only test basic deployment, API accessibility,
# and ingress. Media manager configuration (Radarr/Sonarr) requires an
# initialized Overseerr instance which depends on completing the OAuth flow.
