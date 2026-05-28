# V1 Application Scope

## Context and Problem Statement

Charmarr v1 needs to define which applications to include in the initial release. The scope must be comprehensive enough to validate the architecture across different arr application types, provide actual utility for users, and prove the complete media automation workflow. Too narrow a scope risks missing architectural issues that only emerge when integrating diverse components, while too broad a scope delays the initial release and complicates development.

## Considered Options

* **Option 1: Minimal viable - Single content manager + download client** (Radarr, qBittorrent, Prowlarr)
* **Option 2: Dual content managers** (Radarr, Sonarr, qBittorrent, Prowlarr)
* **Option 3: Complete legacy stack** (Prowlarr, Radarr, Sonarr, qBittorrent, SABnzbd, Plex, Overseerr)
* **Option 4: Full ecosystem** (Complete legacy stack + Lidarr + Jellyfin + Bazarr + Jellyseerr)

## Decision Outcome

Chosen option: **"Option 3: Complete legacy stack"**, because it provides the minimum scope that delivers actual utility while validating architecture across all major arr application categories without delaying v1 indefinitely.

### V1 Core Applications

**Indexer Management:**
- **Prowlarr**: Central indexer manager, synchronizes indexers to all media managers

**Media Managers:**
- **Radarr**: Movie collection management
- **Sonarr**: TV show collection management

**Download Clients:**
- **qBittorrent**: Torrent download client
- **SABnzbd**: Usenet download client

**Media Server:**
- **Plex**: Media streaming server

**Request Management:**
- **Overseerr**: User-facing content request interface

### V1.x Planned Expansions

Subsequent v1.x releases will add:
- **Lidarr**: Music collection management (v1.1)
- **Jellyfin**: Open-source media server alternative to Plex (v1.2)
- **Bazarr**: Subtitle management for Radarr/Sonarr (v1.2)
- **Jellyseerr**: Request management alternative to Overseerr (v1.3)

### Consequences

* Good, because v1 includes enough diversity to validate all interface types (indexer, download-client, media-manager, media-storage, vpn-gateway)
* Good, because v1 delivers a complete, usable media automation platform that replaces Docker Compose setups
* Good, because testing with 7 different applications will reveal architectural issues early
* Good, because both torrent and usenet workflows are validated
* Good, because the architecture supports multiple instances of the same app type (e.g., radarr-4k, radarr-1080p)
* Bad, because v1 doesn't include music management (Lidarr), requiring users who want music automation to wait for v1.1
* Bad, because v1 doesn't include subtitle management (Bazarr), requiring manual subtitle handling
* Bad, because v1 includes only Plex, not Jellyfin, requiring Jellyfin users to wait for v1.2 or configure manually
* Neutral, because 7 charms is ambitious but achievable given pattern reuse across similar applications
