# Track 1

The initial release of Charmarr. A complete media automation stack on Kubernetes.

## Highlights

- **One-command deployment** via OpenTofu module
- **Automatic app configuration** through Juju relations
- **VPN-first architecture** with Gluetun and two-way killswitch
- **Service mesh security** with Istio ambient (opt-in, disabled by default)
- **Built-in TRaSH profiles** via Recyclarr integration
- **Credential rotation** with Juju secrets

## What's Included

### Charms

| Charm | Description |
|-------|-------------|
| `radarr-k8s` | Movie management |
| `sonarr-k8s` | TV show management |
| `prowlarr-k8s` | Indexer management |
| `qbittorrent-k8s` | Torrent downloads |
| `sabnzbd-k8s` | Usenet downloads |
| `plex-k8s` | Media server |
| `overseerr-k8s` | Media requests |
| `recyclarr-k8s` | TRaSH profile sync |
| `flaresolverr-k8s` | Cloudflare bypass |
| `gluetun-k8s` | VPN gateway |
| `charmarr-storage-k8s` | Shared storage |

### OpenTofu Modules

- **charmarr** — Full stack with single Radarr/Sonarr instances
- **charmarr-plus** — Full stack with HD/UHD/Anime variants for Radarr and Sonarr

### Storage Backends

- Hostpath (local disk)
- Native NFS (existing NFS server)
- StorageClass (any CSI driver)

### VPN Providers

Any WireGuard-compatible provider supported by Gluetun. ProtonVPN recommended.

## Known Limitations

- **Ingress port not configurable** — All services use port 443
- **Single node only** — Multi-node clusters not supported
- **No high availability** — Apps cannot scale beyond one replica
- **WireGuard only** — OpenVPN not supported
- **Cilium requires tweaks** — Socket-level LB in host namespace mode required for Istio ambient

## Acknowledgments

Built with [Radarr](https://radarr.video), [Sonarr](https://sonarr.tv), [Prowlarr](https://prowlarr.com), [qBittorrent](https://www.qbittorrent.org), [SABnzbd](https://sabnzbd.org), [Plex](https://www.plex.tv), [Overseerr](https://overseerr.dev), [Recyclarr](https://recyclarr.dev), [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr), [Gluetun](https://github.com/qdm12/gluetun), and [LinuxServer.io](https://www.linuxserver.io) containers.

Powered by [Kubernetes](https://kubernetes.io), [Juju](https://juju.is), [Istio ambient](https://istio.io/latest/docs/ambient/), and [TRaSH Guides](https://trash-guides.info/).

Thanks to [YAMS](https://yams.media) for the inspiration that started this project, and [k8s@home](https://github.com/k8s-at-home) for being a great source of Kubernetes + arr knowledge.
