# Quick Deploy

Charmarr provides pre-configured media stack bundles as [HCL](https://developer.hashicorp.com/terraform/language) modules, deployable with OpenTofu.

!!! note
    Cluster already has Istiod? Use [Manual Deploy](manual.md) instead. If you don't know, your cluster doesn't have one.

## Bundles

| Bundle | ![](../assets/logos/radarr.png){.inline-icon} Radarr | ![](../assets/logos/sonarr.png){.inline-icon} Sonarr |
|--------|--------|--------|
| **charmarr** | 1 (HD) | 1 (HD) |
| **charmarr-plus** | 3 (HD, UHD, Anime) | 3 (HD, UHD, Anime) |

Both bundles include:

<table>
  <tr>
    <td><img src="../../assets/logos/plex.png" class="inline-icon"> Plex</td>
    <td><img src="../../assets/logos/overseerr.png" class="inline-icon"> Overseerr</td>
    <td><img src="../../assets/logos/prowlarr.png" class="inline-icon"> Prowlarr</td>
    <td><img src="../../assets/logos/flaresolverr.png" class="inline-icon"> FlareSolverr</td>
  </tr>
  <tr>
    <td><img src="../../assets/logos/qbittorrent.png" class="inline-icon"> qBittorrent</td>
    <td><img src="../../assets/logos/sabnzbd.png" class="inline-icon"> SABnzbd</td>
    <td><img src="../../assets/logos/gluetun.png" class="inline-icon"> Gluetun</td>
    <td><img src="../../assets/logos/recyclarr.png" class="inline-icon"> Recyclarr</td>
  </tr>
</table>

!!! note
    charmarr-plus has slightly higher CPU requirements due to additional Radarr/Sonarr instances. During initial deployment, expect higher CPU and RAM usage. It flatlines once settled.

---

## Charmarr

Single Radarr and Sonarr with HD TRaSH profiles pre-configured.

### 1. Create a `main.tf` file

See the [OpenTofu docs](https://opentofu.org/docs/) if you're curious about how it works.

```hcl
variable "wireguard_private_key" {
  type      = string
  sensitive = true
  default   = ""
}

module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  model = "charmarr"

  # Storage
  storage_backend = "hostpath"
  hostpath        = "/mnt/storage/charmarr"

  # VPN
  enable_vpn            = true
  wireguard_private_key = var.wireguard_private_key
  vpn_provider          = "protonvpn"
  cluster_cidrs         = "10.1.0.0/16,10.152.183.0/24,192.168.1.0/24"
}
```

### 2. Configure Variables

#### Storage

Shared storage enables hardlinks between download clients and media managers. See [Storage](../charms/storage.md) for why this matters.

**Hostpath** (recommended for single-node) - Storage on the same node as the cluster:

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  storage_backend = "hostpath"
  hostpath        = "/path/to/your/media"
}
```

!!! warning
    Avoid NFS on the same node. Loopback mounts can cause deadlocks.

**Native NFS** (recommended for multi-node) - External NFS server:

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  storage_backend = "native-nfs"
  nfs_server      = "192.168.1.100"
  nfs_path        = "/export/charmarr"
}
```

**StorageClass** - Custom CSI driver (Rook-Ceph, etc.):

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  storage_backend = "storage-class"
  storage_class   = "rook-ceph-block"
  storage_size    = "1Ti"
}
```

!!! warning
    StorageClass is experimental. Requires careful configuration of `storage_size`, `access_mode`, and `cleanup_on_remove`. Trivial for hostpath and native-nfs, not so for CSI drivers.

**File Ownership (Hostpath & NFS)**

For hostpath and NFS backends, the storage path must be owned by UID/GID 1000:1000 by default:

```bash
sudo chown -R 1000:1000 /path/to/your/media
```

If your path is owned by a different UID/GID, configure the storage charm to match:

```bash
# Check current ownership
ls -ln /path/to/your/media
```

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  storage = {
    config = {
      puid = "1001"
      pgid = "1001"
    }
  }
}
```

For NFS, ensure the NFS export allows write access for the configured PUID/PGID.

For StorageClass with CSI drivers, this is driver-dependent. Block storage drivers typically handle ownership automatically, while shared filesystem drivers (CephFS, NFS-based CSI) follow the same rules as NFS.

#### VPN

By default, `enable_vpn = true` deploys Gluetun and integrates it with qBittorrent, SABnzbd, and Prowlarr. All traffic from these apps routes through a VPN tunnel and their external IP is anonymized. See [Networking](../security/network.md) for how this works.

**Provider**

Only WireGuard is supported. OpenVPN is not supported.

| Provider | Value |
|----------|-------|
| ProtonVPN | `protonvpn` (recommended) |
| NordVPN | `nordvpn` |
| Mullvad | `mullvad` |
| Private Internet Access | `pia` |
| Surfshark | `surfshark` |
| IVPN | `ivpn` |
| Windscribe | `windscribe` |
| Custom WireGuard | `custom` (experimental) |

For most commercial VPNs, only the `wireguard_private_key` is needed. Custom WireGuard setups require additional variables: `wireguard_addresses`, `vpn_endpoint_ip`, `vpn_endpoint_port`, and `wireguard_public_key`.

**Cluster CIDRs**

Comma-separated list of CIDRs to exclude from VPN routing (required when VPN is enabled). Include:

- **Pod CIDR** - K8s pod network
- **Service CIDR** - K8s service network
- **LAN CIDR** - Your local network

**MicroK8s defaults:**

| CIDR | Default |
|------|---------|
| Pod | `10.1.0.0/16` |
| Service | `10.152.183.0/24` |

**Find CIDRs with kubectl:**

```bash
# Pod CIDR (Calico CNI)
kubectl get ippools -o jsonpath='{.items[*].spec.cidr}'

# Service CIDR (check kubernetes service IP, typically x.x.x.0/24)
kubectl get svc kubernetes -o jsonpath='{.spec.clusterIP}'
```

**Find your LAN CIDR:**

```bash
ip -4 addr show | grep -oP 'inet \K[\d./]+'
```

Look for your network interface IP (e.g., `192.168.1.100/24` means your LAN CIDR is `192.168.1.0/24`).

**Disabling VPN**

If you use a different tunneling solution (e.g., Tailscale exit node, network-level VPN), you can disable the built-in VPN:

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  enable_vpn = false

  qbittorrent = {
    config = {
      "unsafe-mode" = "true"
    }
  }

  sabnzbd = {
    config = {
      "unsafe-mode" = "true"
    }
  }
}
```

When `enable_vpn = false`, Gluetun is not deployed and download clients are not integrated with a VPN gateway. You must also enable `unsafe-mode` on qBittorrent and SABnzbd for them to start without VPN protection.

!!! warning
    Without VPN integration, your real IP is exposed to torrent trackers and usenet providers. Only disable VPN if you have an alternative tunneling solution in place.

#### Plex Hardware Transcoding

If your hardware supports it:

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  plex = {
    hardware_transcoding = true
  }
}
```

#### Istio

Enable Istio for ingress and mesh security (see [Compatibility Checklist](prerequisites.md#compatibility-checklist) first):

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  enable_istio = true
  enable_mesh  = true

  # Only needed if not using MicroK8s
  istio = {
    config = {
      platform = "minikube"  # see table below
    }
  }
}
```

| Distribution | `platform` value |
|--------------|------------------|
| MicroK8s | `microk8s` (default) |
| Minikube | `minikube` |
| Standard K8s (GKE, EKS, AKS, kubeadm) | `""` |
| K3s | `k3s` |
| k3d | `k3d` |

**Path Prefixes**

The arr apps and download clients are configured with path prefixes for ingress routing:

| App | Default Path |
|-----|--------------|
| Radarr | `/radarr` |
| Sonarr | `/sonarr` |
| Prowlarr | `/prowlarr` |
| qBittorrent | `/qbittorrent` |
| SABnzbd | `/sabnzbd` |

With Istio ingress, these paths are automatically configured. If you're using your own ingress controller, configure it to route these paths to the respective services.

To use different paths, or set `"/"` to serve at root (no path prefix):

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  radarr = {
    ingress_path = "/movies"
  }

  qbittorrent = {
    ingress_path = "/"  # serve at root
  }
}
```

### 3. Deploy

```bash
tofu init && TF_VAR_wireguard_private_key="your-key" tofu apply -auto-approve
```

Or without VPN (when `enable_vpn = false`):

```bash
tofu init && tofu apply -auto-approve
```

See the [charmarr module](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr) for all available variables.

---

## Charmarr Plus

Three Radarrs (HD, UHD, Anime) and three Sonarrs (HD, UHD, Anime) with appropriate TRaSH profiles.

### 1. Create a `main.tf` file

```hcl
variable "wireguard_private_key" {
  type      = string
  sensitive = true
  default   = ""
}

module "charmarr_plus" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr-plus?ref=main"

  model = "charmarr"

  # Storage
  storage_backend = "hostpath"
  hostpath        = "/mnt/storage/charmarr"

  # VPN
  enable_vpn            = true
  wireguard_private_key = var.wireguard_private_key
  vpn_provider          = "protonvpn"
  cluster_cidrs         = "10.1.0.0/16,10.152.183.0/24,192.168.1.0/24"
}
```

### 2. Configure Variables

Same as charmarr. See [Storage](#storage), [VPN](#vpn), and [Istio](#istio) above.

### 3. Deploy

```bash
tofu init && TF_VAR_wireguard_private_key="your-key" tofu apply -auto-approve
```

Or without VPN (when `enable_vpn = false`):

```bash
tofu init && tofu apply -auto-approve
```

See the [charmarr-plus module](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr-plus) for all available variables.

!!! tip
    Want a truly custom Charmarr with different Radarrs, multiple download clients, etc.? Use the [charmarr](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr) and [charmarr-plus](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr-plus) modules as templates to create your own charmarr bundle.

!!! tip
    After deployment, the [Manual Deploy](manual.md) page can be used as a reference to customize your stack with the Juju CLI. It's fun.

---

## Making Changes

Edit your `main.tf` and reapply. OpenTofu calculates the diff and applies only what changed.

For example, to enable Istio ingress later:

```hcl
module "charmarr" {
  # ... existing config ...

  enable_istio = true
  enable_mesh  = true
}
```

```bash
tofu apply
```

See the [OpenTofu CLI docs](https://opentofu.org/docs/cli/commands/apply/) for more.

---

## Removing Charmarr

To tear down the deployment:

```bash
tofu destroy
```

---

<div style="display: flex; justify-content: space-between" markdown>
<div markdown>
[:octicons-arrow-left-24: Prerequisites](prerequisites.md)
</div>
<div markdown>
[Post-Deploy :octicons-arrow-right-24:](post-deploy.md)
</div>
</div>
