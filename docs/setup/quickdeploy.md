# Quick Deploy

Charmarr provides pre-configured media stack bundles as [HCL](https://developer.hashicorp.com/terraform/language) modules, deployable with OpenTofu.

!!! warning
    If your K8s cluster already has an Istiod control plane running, Quick Deploy won't work as it deploys its own Istiod. Use [Manual Deploy](manual.md) instead.

## Bundles

| Bundle | <img src="/assets/logos/radarr.png" class="inline-icon"> Radarr | <img src="/assets/logos/sonarr.png" class="inline-icon"> Sonarr |
|--------|--------|--------|
| **charmarr** | 1 (HD) | 1 (HD) |
| **charmarr-plus** | 3 (HD, UHD, Anime) | 3 (HD, UHD, Anime) |

Both bundles include:

<table>
  <tr>
    <td><img src="/assets/logos/plex.png" class="inline-icon"> Plex</td>
    <td><img src="/assets/logos/overseerr.png" class="inline-icon"> Overseerr</td>
    <td><img src="/assets/logos/prowlarr.png" class="inline-icon"> Prowlarr</td>
    <td><img src="/assets/logos/flaresolverr.png" class="inline-icon"> FlareSolverr</td>
  </tr>
  <tr>
    <td><img src="/assets/logos/qbittorrent.png" class="inline-icon"> qBittorrent</td>
    <td><img src="/assets/logos/sabnzbd.png" class="inline-icon"> SABnzbd</td>
    <td><img src="/assets/logos/gluetun.png" class="inline-icon"> Gluetun</td>
    <td><img src="/assets/logos/recyclarr.png" class="inline-icon"> Recyclarr</td>
  </tr>
</table>

!!! note
    charmarr-plus has slightly higher CPU requirements due to additional Radarr/Sonarr instances. During initial deployment, expect higher CPU and RAM usage. It flatlines once settled.

---

## Charmarr

Single Radarr and Sonarr with HD TRaSH profiles pre-configured.

### 1. Create main.tf

```hcl
variable "wireguard_private_key" {
  type      = string
  sensitive = true
}

module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  model                 = "charmarr"
  wireguard_private_key = var.wireguard_private_key
  vpn_provider          = "protonvpn"
  cluster_cidrs         = "10.1.0.0/16,10.152.183.0/24,192.168.1.0/24"
  storage_backend       = "hostpath"
  hostpath              = "/mnt/storage/charmarr"
}
```

### 2. Configure Variables

#### VPN Provider

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

#### Cluster CIDRs

Comma-separated list of CIDRs to exclude from VPN routing. Include:

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

#### Storage

**Hostpath** - Storage on the same node as the cluster:

```hcl
storage_backend = "hostpath"
hostpath        = "/path/to/your/media"
```

!!! warning
    Avoid NFS on the same node. Loopback mounts can cause deadlocks.

**Native NFS** - External NFS server:

```hcl
storage_backend = "native-nfs"
nfs_server      = "192.168.1.100"
nfs_path        = "/export/charmarr"
```

**StorageClass** - Custom CSI driver (Rook-Ceph, etc.):

```hcl
storage_backend = "storage-class"
storage_class   = "rook-ceph-block"
storage_size    = "1Ti"
```

!!! warning
    StorageClass is experimental. Requires careful configuration of `storage_size`, `access_mode`, and `cleanup_on_remove`. Trivial for hostpath and native-nfs, not so for CSI drivers.

#### Plex Hardware Transcoding

If your hardware supports it:

```hcl
plex = {
  hardware_transcoding = true
}
```

### 3. Deploy

```bash
tofu init && TF_VAR_wireguard_private_key="your-key" tofu apply -auto-approve
```

See the [charmarr module](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr) for all available variables.

---

## Charmarr Plus

Three Radarrs (HD, UHD, Anime) and three Sonarrs (HD, UHD, Anime) with appropriate TRaSH profiles.

### 1. Create main.tf

```hcl
variable "wireguard_private_key" {
  type      = string
  sensitive = true
}

module "charmarr_plus" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr-plus?ref=main"

  model                 = "charmarr"
  wireguard_private_key = var.wireguard_private_key
  vpn_provider          = "protonvpn"
  cluster_cidrs         = "10.1.0.0/16,10.152.183.0/24,192.168.1.0/24"
  storage_backend       = "hostpath"
  hostpath              = "/mnt/storage/charmarr"
}
```

### 2. Configure Variables

Same as charmarr. See [VPN Provider](#vpn-provider), [Cluster CIDRs](#cluster-cidrs), and [Storage](#storage) above.

### 3. Deploy

```bash
tofu init && TF_VAR_wireguard_private_key="your-key" tofu apply -auto-approve
```

See the [charmarr-plus module](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr-plus) for all available variables.

!!! tip
    Want a truly custom Charmarr with different Radarrs, multiple download clients, etc.? Use the [charmarr](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr) and [charmarr-plus](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr-plus) modules as templates to create your own charmarr bundle.

!!! tip
    After deployment, the [Manual Deploy](manual.md) page can be used as a reference to customize your stack with the Juju CLI. It's fun.

---

## Making Changes

Edit your `main.tf` and reapply:

```bash
tofu apply
```

OpenTofu calculates the diff and applies only what changed. See the [OpenTofu CLI docs](https://opentofu.org/docs/cli/commands/apply/) for more.

---

<div style="display: flex; justify-content: space-between" markdown>
<div markdown>
[:octicons-arrow-left-24: Prerequisites](prerequisites.md)
</div>
<div markdown>
[Post-Deploy :octicons-arrow-right-24:](post-deploy.md)
</div>
</div>
