# Manual Deployment

Deploy and configure apps with the Juju CLI. More control, more fun.

Think of it like connecting Lego blocks. Each charm is a block, and relations snap them together. It's slower than the HCL bundles, but by the end you'll know exactly what's deployed, what's connected to what, and why.

Perfect for learning, debugging, or building something the pre-built bundles don't cover.

!!! tip
    Open a second terminal and run `juju status --integrations --watch 1s` to watch your deployment come alive as you run commands.

---

## 1. Infrastructure

First, we lay the groundwork: service mesh, ingress gateways, shared storage, and VPN.

### Istio Control Plane

!!! note
    Skip this step if your cluster already has an Istiod control plane. If you are unsure, you don't have one.

```bash
juju deploy istio-k8s --trust --channel=2/edge istio
juju deploy istio-beacon-k8s --trust --channel=2/edge beacon
```

### Ingress Gateways

Three ingress gateways are needed:

- **arr-ingress** for arr apps and download clients (supports path prefixes like `/radarr`, `/sonarr`)
- **plex-ingress** for Plex (serves at root only)
- **overseerr-ingress** for Overseerr (serves at root only)

```bash
juju deploy istio-ingress-k8s --trust --channel=2/edge arr-ingress
juju deploy istio-ingress-k8s --trust --channel=2/edge plex-ingress
juju deploy istio-ingress-k8s --trust --channel=2/edge overseerr-ingress
```

### Storage

```bash
juju deploy charmarr-storage-k8s --trust --channel=latest/edge storage
```

Configure based on your storage backend:

**Hostpath** (storage on same node):

```bash
juju config storage backend-type=hostpath hostpath=/path/to/media
```

**Native NFS** (external NFS server):

```bash
juju config storage backend-type=native-nfs nfs-server=192.168.1.100 nfs-path=/export/charmarr
```

**StorageClass** (CSI driver):

```bash
juju config storage backend-type=storage-class storage-class=your-storage-class size=1Ti
```

### VPN Gateway

Deploy gluetun:

```bash
juju deploy gluetun-k8s --trust --channel=latest/edge gluetun
```

Create and grant the VPN secret (key is encrypted at rest):

```bash
juju add-secret vpn-key private-key="your-wireguard-private-key"
juju grant-secret vpn-key gluetun
```

Configure gluetun:

```bash
juju config gluetun \
  wireguard-private-key-secret=secret:vpn-key \
  vpn-provider=protonvpn \
  cluster-cidrs="10.1.0.0/16,10.152.183.0/24,192.168.1.0/24"
```

See [VPN Provider](quickdeploy.md#vpn-provider) and [Cluster CIDRs](quickdeploy.md#cluster-cidrs) for help determining these values.

---

## 2. Media Apps

Now for the fun part: the actual media apps.

### Download Clients

```bash
juju deploy qbittorrent-k8s --trust --channel=latest/edge qbittorrent
juju deploy sabnzbd-k8s --trust --channel=latest/edge sabnzbd
```

Configure ingress paths and credential rotation:

```bash
juju config qbittorrent ingress-path=/qbt credential-rotation=monthly
juju config sabnzbd ingress-path=/sab credential-rotation=monthly
```

`credential-rotation` automatically rotates credentials on the specified interval (`disabled`, `daily`, `monthly`, `yearly`) and syncs to related apps.

Want more download clients? Deploy additional instances with different names.

### Media Managers

```bash
juju deploy radarr-k8s --trust --channel=latest/edge radarr
juju deploy sonarr-k8s --trust --channel=latest/edge sonarr
```

Configure variant and trash profiles:

| Variant | Root Folder | Default TRaSH Profile |
|---------|-------------|----------------------|
| `standard` | /data/media/movies or /data/media/tv | None |
| `4k` | /data/media/movies-uhd or /data/media/tv-uhd | uhd-bluray-web |
| `anime` | /data/media/anime/movies or /data/media/anime/tv | anime |

```bash
# Standard HD instance (set trash-profiles manually)
juju config radarr variant=standard trash-profiles=hd-bluray-web

# 4K instance (uses uhd-bluray-web by default)
juju deploy radarr-k8s --trust --channel=latest/edge radarr-4k
juju config radarr-4k variant=4k ingress-path=/radarr-4k
```

Deploy as many managers as needed with unique names and ingress paths.

### Indexer

```bash
juju deploy prowlarr-k8s --trust --channel=latest/edge prowlarr
juju deploy flaresolverr-k8s --trust --channel=latest/edge flaresolverr
```

### Media Server & Requester

```bash
juju deploy plex-k8s --trust --channel=latest/edge plex
juju deploy overseerr-k8s --trust --channel=latest/edge overseerr
```

Enable hardware transcoding for Plex (requires Intel QuickSync and Plex Pass):

```bash
juju config plex hardware-transcoding=true
```

---

## 3. Connecting Apps

Apps are deployed but isolated. Relations snap them together. This is where the Lego blocks click.

When you integrate two apps, they exchange information like URLs, API keys, and configuration details. This is how Radarr knows where to find qBittorrent, how Prowlarr registers itself with Sonarr, and how Overseerr discovers your media managers. No manual copying of URLs or API keys in web UIs.

Sensitive information (API keys, credentials) is shared via Juju secrets and encrypted at rest.

### Storage

Connect apps that need shared media storage:

```bash
juju integrate radarr:media-storage storage:media-storage
juju integrate sonarr:media-storage storage:media-storage
juju integrate plex:media-storage storage:media-storage
juju integrate qbittorrent:media-storage storage:media-storage
juju integrate sabnzbd:media-storage storage:media-storage
```

### VPN Tunnel

Connect download clients and indexer to VPN:

```bash
juju integrate qbittorrent:vpn-gateway gluetun:vpn-gateway
juju integrate sabnzbd:vpn-gateway gluetun:vpn-gateway
juju integrate prowlarr:vpn-gateway gluetun:vpn-gateway
```

### Cloudflare Bypass

Connect FlareSolverr to Prowlarr:

```bash
juju integrate prowlarr:flaresolverr flaresolverr:flaresolverr
```

### Download Clients to Managers

```bash
juju integrate radarr:download-client qbittorrent:download-client
juju integrate radarr:download-client sabnzbd:download-client
juju integrate sonarr:download-client qbittorrent:download-client
juju integrate sonarr:download-client sabnzbd:download-client
```

### Indexer to Managers

```bash
juju integrate radarr:media-indexer prowlarr:media-indexer
juju integrate sonarr:media-indexer prowlarr:media-indexer
```

### Media Server to Managers

```bash
juju integrate plex:media-manager radarr:media-manager
juju integrate plex:media-manager sonarr:media-manager
```

### Requester to Managers & Server

```bash
juju integrate overseerr:media-manager radarr:media-manager
juju integrate overseerr:media-manager sonarr:media-manager
juju integrate overseerr:media-server plex:media-server
```

### Ingress

Connect apps to their ingress gateways:

```bash
# Arr apps and download clients
juju integrate radarr:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate sonarr:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate prowlarr:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate qbittorrent:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate sabnzbd:istio-ingress-route arr-ingress:istio-ingress-route

# Plex
juju integrate plex:istio-ingress-route plex-ingress:istio-ingress-route

# Overseerr
juju integrate overseerr:istio-ingress-route overseerr-ingress:istio-ingress-route
```

### Service Mesh (Optional)

For encrypted and firewalled traffic between apps:

```bash
juju integrate radarr:service-mesh beacon:service-mesh
juju integrate sonarr:service-mesh beacon:service-mesh
juju integrate prowlarr:service-mesh beacon:service-mesh
juju integrate plex:service-mesh beacon:service-mesh
juju integrate overseerr:service-mesh beacon:service-mesh
juju integrate qbittorrent:service-mesh beacon:service-mesh
juju integrate sabnzbd:service-mesh beacon:service-mesh
juju integrate flaresolverr:service-mesh beacon:service-mesh
```

---

## Charm Configuration Reference

| Charm | Charmhub |
|-------|----------|
| charmarr-storage-k8s | [configurations](https://charmhub.io/charmarr-storage-k8s/configurations) |
| gluetun-k8s | [configurations](https://charmhub.io/gluetun-k8s/configurations) |
| qbittorrent-k8s | [configurations](https://charmhub.io/qbittorrent-k8s/configurations) |
| sabnzbd-k8s | [configurations](https://charmhub.io/sabnzbd-k8s/configurations) |
| radarr-k8s | [configurations](https://charmhub.io/radarr-k8s/configurations) |
| sonarr-k8s | [configurations](https://charmhub.io/sonarr-k8s/configurations) |
| prowlarr-k8s | [configurations](https://charmhub.io/prowlarr-k8s/configurations) |
| flaresolverr-k8s | [configurations](https://charmhub.io/flaresolverr-k8s/configurations) |
| plex-k8s | [configurations](https://charmhub.io/plex-k8s/configurations) |
| overseerr-k8s | [configurations](https://charmhub.io/overseerr-k8s/configurations) |

---

<div style="display: flex; justify-content: space-between" markdown>
<div markdown>
[:octicons-arrow-left-24: Prerequisites](prerequisites.md)
</div>
<div markdown>
[Post-Deployment :octicons-arrow-right-24:](post-deploy.md)
</div>
</div>
