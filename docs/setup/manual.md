# Manual Deploy

Deploy and configure apps with the Juju CLI. More control, more fun.

Think of it like connecting Lego blocks. Each charm is a block, and relations snap them together. It's slower and more effort than the HCL bundles, but by the end you'll know exactly what's deployed, what's connected to what, and why.

Perfect for learning, debugging, or building something the pre-built bundles don't cover.

!!! tip
    Open a second terminal and run `juju status --integrations --watch 1s` to watch your deployment come alive as you run commands.

---

## 1. Infrastructure Apps

First, we lay the groundwork: shared storage and VPN.

### Storage

Shared storage enables hardlinks between download clients and media managers. See [Storage](../charms/storage.md) for why this matters.

```bash
juju deploy charmarr-storage-k8s --trust --channel=latest/edge storage
```

Configure based on your storage backend:

**Hostpath** (recommended for single-node):

```bash
juju config storage backend-type=hostpath hostpath=/path/to/media
```

**Native NFS** (recommended for multi-node):

```bash
juju config storage backend-type=native-nfs nfs-server=192.168.1.100 nfs-path=/export/charmarr
```

**StorageClass** (CSI driver):

```bash
juju config storage backend-type=storage-class storage-class=your-storage-class size=1Ti
```

**File Ownership (Hostpath & NFS)**

For hostpath and NFS backends, the storage path must be owned by UID/GID 1000:1000 by default:

```bash
sudo chown -R 1000:1000 /path/to/your/media
```

If your path is owned by a different UID/GID, configure the storage charm to match:

```bash
# Check current ownership
ls -ln /path/to/your/media

# Configure storage charm with the actual UID/GID
juju config storage puid=1001 pgid=1001
```

For NFS, ensure the NFS export allows write access for the configured PUID/PGID.

For StorageClass with CSI drivers, this is driver-dependent. Block storage drivers typically handle ownership automatically, while shared filesystem drivers (CephFS, NFS-based CSI) follow the same rules as NFS.

### VPN Gateway

The VPN gateway anonymizes external traffic from privacy-sensitive charms. See [VPN Gateway](../charms/vpn-gateway.md) for how it works.

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

!!! warning "OpenVPN Support"
    OpenVPN is not officially supported. If your VPN provider only supports OpenVPN, or you need to pass custom environment variables to Gluetun, use the `custom-overrides` config to enter override mode. In override mode, WireGuard validation is bypassed and the provided JSON is merged on top of the charm's built-in environment.

    Unlike `wireguard-private-key-secret` which is stored as a Juju secret and encrypted at rest, `custom-overrides` is plain text charm config. Credentials passed here are not encrypted.

    ```bash
    juju config gluetun \
      vpn-provider=protonvpn \
      cluster-cidrs="10.1.0.0/16,10.152.183.0/24,192.168.1.0/24" \
      custom-overrides='{"VPN_TYPE": "openvpn", "OPENVPN_USER": "your-username", "OPENVPN_PASSWORD": "your-password"}'
    ```

    Override mode relaxes config validation. Misconfiguration may result in silent failures that require inspecting the Gluetun container logs to diagnose. See the [Gluetun wiki](https://github.com/qdm12/gluetun-wiki) for available environment variables.

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

`credential-rotation` automatically rotates credentials on the specified interval (`disabled`, `daily`, `monthly`, `yearly`) and syncs to related apps. See [Secrets](../security/secrets.md) for how rotation works.

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

Connect apps to shared media storage. Required for hardlinks and atomic copies.

```bash
juju integrate radarr:media-storage storage:media-storage
juju integrate sonarr:media-storage storage:media-storage
juju integrate plex:media-storage storage:media-storage
juju integrate qbittorrent:media-storage storage:media-storage
juju integrate sabnzbd:media-storage storage:media-storage
```

### VPN Tunnel

Connect download clients and indexer to VPN. Routes traffic through Gluetun's tunnel with kill switch protection.

```bash
juju integrate qbittorrent:vpn-gateway gluetun:vpn-gateway
juju integrate sabnzbd:vpn-gateway gluetun:vpn-gateway
juju integrate prowlarr:vpn-gateway gluetun:vpn-gateway
```

A two-way killswitch protects your privacy:

- If the VPN connection drops, Gluetun's internal killswitch blocks traffic
- If the Gluetun pod dies, Kubernetes NetworkPolicies block traffic

**Verify pod external IP (should show VPN IP, not your real IP):**

```bash
kubectl exec -n charmarr deploy/qbittorrent -- wget -qO- ifconfig.me
kubectl exec -n charmarr deploy/sabnzbd -- wget -qO- ifconfig.me
kubectl exec -n charmarr deploy/prowlarr -- wget -qO- ifconfig.me
```

**Skipping VPN**

If you use a different tunneling solution, skip Gluetun deployment and VPN integrations. You must enable `unsafe-mode` on qBittorrent and SABnzbd for them to start without VPN protection:

```bash
juju config qbittorrent unsafe-mode=true
juju config sabnzbd unsafe-mode=true
```

!!! warning
    Without VPN integration, your real IP is exposed to torrent trackers and usenet providers.

### Cloudflare Bypass

Connect FlareSolverr to Prowlarr. Solves captchas for indexers behind Cloudflare protection.

```bash
juju integrate prowlarr:flaresolverr flaresolverr:flaresolverr
```

### Download Clients to Managers

Connect Radarr/Sonarr to qBittorrent and SABnzbd. Sends download requests and monitors progress.

```bash
juju integrate radarr:download-client qbittorrent:download-client
juju integrate radarr:download-client sabnzbd:download-client
juju integrate sonarr:download-client qbittorrent:download-client
juju integrate sonarr:download-client sabnzbd:download-client
```

### Indexer to Managers

Connect Prowlarr to Radarr/Sonarr. Syncs indexers automatically across all managers.

```bash
juju integrate radarr:media-indexer prowlarr:media-indexer
juju integrate sonarr:media-indexer prowlarr:media-indexer
```

### Media Server to Managers

Connect Plex to Radarr/Sonarr. Adds required libraries automatically to Plex.

```bash
juju integrate plex:media-manager radarr:media-manager
juju integrate plex:media-manager sonarr:media-manager
```

### Requester to Managers & Server

Connect Overseerr to Radarr/Sonarr and Plex. Enables user requests and library visibility.

```bash
juju integrate overseerr:media-manager radarr:media-manager
juju integrate overseerr:media-manager sonarr:media-manager
juju integrate overseerr:media-server plex:media-server
```

---

## 4. Istio (Optional)

Istio provides ingress and service mesh security. Check the [Compatibility Checklist](prerequisites.md#compatibility-checklist) before enabling. If you skip Istio, handle ingress yourself (e.g., Nginx Ingress, Traefik, or NodePorts).

**Path Prefixes**

The arr apps and download clients are configured with default path prefixes:

| App | Default Path |
|-----|--------------|
| Radarr | `/radarr` |
| Sonarr | `/sonarr` |
| Prowlarr | `/prowlarr` |
| qBittorrent | `/qbittorrent` |
| SABnzbd | `/sabnzbd` |

With Istio ingress, these paths are automatically configured. If you're using your own ingress controller, configure it to route these paths to the respective services.

To use different paths, or set `/` to serve at root (no path prefix):

```bash
juju config radarr ingress-path=/movies
juju config qbittorrent ingress-path=/
```

### Deploy Istio

**Control Plane:**

```bash
juju deploy istio-k8s --trust --channel=2/edge istio
```

!!! warning
    Skip istio-k8s if your cluster already has an Istiod control plane. If you are unsure, you don't have one.

**Ingress Gateways:**

```bash
juju deploy istio-ingress-k8s --trust --channel=2/edge arr-ingress
juju deploy istio-ingress-k8s --trust --channel=2/edge plex-ingress
juju deploy istio-ingress-k8s --trust --channel=2/edge overseerr-ingress
```

**Beacon (for service mesh):**

Required only for mTLS and authorization policies. See [Networking](../security/network.md) for details.

```bash
juju deploy istio-beacon-k8s --trust --channel=2/edge beacon
```

### Connect Ingress

Expose app UIs via LoadBalancer IPs.

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

### Connect Service Mesh

Requires Beacon. Enables mTLS and authorization policies.

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

## Managing Apps

Remove a relation:

```bash
juju remove-relation radarr:download-client qbittorrent:download-client
```

Remove an app:

```bash
juju remove-application qbittorrent
```

For the full list of commands, see the [Juju CLI reference](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/).

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
[Post-Deploy :octicons-arrow-right-24:](post-deploy.md)
</div>
</div>
