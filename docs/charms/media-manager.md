# Media Manager

## Radarr & Sonarr

The Radarr charm (`radarr-k8s`) and Sonarr charm (`sonarr-k8s`) manage Radarr and Sonarr in your Charmarr stack. Radarr handles movies, Sonarr handles TV shows. The charms share nearly identical logic, differing only in ports, media types, and folder paths.

### Relations

The charms talk to other charms to figure out how to set everything up. The order in which these connections happen doesn't matter. The charm sorts it out.

| Connects To | Interface | What It Learns |
|-------------|-----------|----------------|
| **Storage** | `media-storage` | Where the media root is, UID/GID for file permissions |
| **Prowlarr** | `media-indexer` | Publishes API URL so Prowlarr can push indexers |
| **qBittorrent/SABnzbd** | `download-client` | Gets their connection info, configures them as download clients |
| **Plex** | `media-manager` | Publishes root folders and content type so Plex can create libraries |
| **Overseerr** | `media-manager` | Publishes API URL, quality profiles, root folders so Overseerr can send requests |
| **VPN Gateway** | `vpn-gateway` | Optional VPN routing (if related) |
| **Ingress** | `istio_ingress_route` | Enables external access |

The charm aggressively reconciles download clients. If you manually add a download client in Radarr/Sonarr that isn't a Juju relation, it gets deleted. Charms are declarative and Charmarr is designed to ✨just work✨.

An API key is generated automatically and stored as a Juju secret. It [rotates periodically](../security/secrets.md) if configured.

### Recyclarr Integration

Each Radarr/Sonarr charm includes a [Recyclarr](https://recyclarr.dev/) sidecar container that syncs quality profiles from [TRaSH Guides](https://trash-guides.info/). This is optional but enabled by default for 4K and anime variants.

| Variant | Default Profiles |
|---------|------------------|
| standard | None (user configures manually) |
| 4k | `uhd-bluray-web` |
| anime | `anime` |

Recyclarr runs on every reconcile if configured. It's idempotent, so running it multiple times is safe. The profiles it creates are published to Overseerr automatically.

!!! note
    The charm allows setting or overriding default profiles using the `trash-profiles` config option. See [Manual Deploy](../setup/manual.md#media-managers).

### Lifecycle

```mermaid
sequenceDiagram
    participant Storage
    participant RC as Radarr/Sonarr Charm
    participant App as Radarr/Sonarr App
    participant DC as Download Clients

    RC->>Storage: Where's the media?
    Storage-->>RC: /data + UID/GID
    Note over RC: Waits if no reply

    RC->>RC: Create API key
    RC->>App: Start
    App-->>RC: Ready
    Note over RC: Waits if no reply

    RC->>App: Sync TRaSH profiles

    DC-->>RC: Here's our connection info
    RC->>App: Configure download clients

    RC->>App: Create root folder
    RC-->>Prowlarr: Here's my API URL
    RC-->>Plex/Overseerr: Here's my profiles and folders
```

### Variants

Deploy multiple instances with different variants to separate content:

| Variant | Radarr Root Folder | Sonarr Root Folder |
|---------|--------------------|--------------------|
| standard | `/data/media/movies` | `/data/media/tv` |
| 4k | `/data/media/movies-uhd` | `/data/media/tv-uhd` |
| anime | `/data/media/anime/movies` | `/data/media/anime/tv` |

Each variant uses its app name as the download client category (e.g., `radarr`, `radarr-4k`). The download clients create matching categories automatically.

### Configuration

See [radarr-k8s on Charmhub](https://charmhub.io/radarr-k8s) and [sonarr-k8s on Charmhub](https://charmhub.io/sonarr-k8s) for all options.
