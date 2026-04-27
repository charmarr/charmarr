# VPN Gateway

## Gluetun

The Gluetun charm (`gluetun-k8s`) manages the [gluetun](https://github.com/qdm12/gluetun) VPN gateway in your Charmarr stack. Gluetun routes traffic from connected charms through a VPN tunnel to protect your privacy.

### Relations

The charm talks to other charms to figure out how to set everything up. The order in which these connections happen doesn't matter. The charm sorts it out.

| Connects To | Interface | What It Provides |
|-------------|-----------|------------------|
| **qBittorrent/SABnzbd/Prowlarr** | `vpn-gateway` | VPN tunnel routing for their traffic |

When charms connect, Gluetun automatically configures them to route all external traffic through the VPN. If the VPN connection drops, traffic is blocked (killswitch).

### How It Works

Without a VPN gateway, charms connect directly to the internet and your home IP is exposed to torrent trackers, indexers, and usenet providers. The Gluetun charm fixes this by doing two things when it starts:

1. Uses [gluetun](https://github.com/qdm12/gluetun) to establish a WireGuard VPN tunnel
2. Bootstraps a [pod-gateway](https://github.com/angelnu/pod-gateway) server (init container + sidecar) onto its pod

When a charm connects to Gluetun, the Gluetun charm provides gateway info. The connecting charm uses this info to bootstrap a pod-gateway client (init container + sidecar) onto its pod. The pod-gateway client connects to the pod-gateway server using this gateway info to form a VXLAN overlay network. A single Gluetun pod serves multiple charms.

<center>

```mermaid
flowchart LR
    subgraph qBittorrent Pod
        QB[qBittorrent]
        PGC1[Pod Gateway Client]
    end

    subgraph SABnzbd Pod
        SAB[SABnzbd]
        PGC2[Pod Gateway Client]
    end

    subgraph Prowlarr Pod
        PR[Prowlarr]
        PGC3[Pod Gateway Client]
    end

    subgraph Gluetun Pod
        PGS[Pod Gateway Server]
        subgraph Gluetun App
            WG[WireGuard Tunnel]
        end
    end

    QB --> PGC1
    SAB --> PGC2
    PR --> PGC3

    PGC1 -->|VXLAN| PGS
    PGC2 -->|VXLAN| PGS
    PGC3 -->|VXLAN| PGS

    PGS --> WG
    WG --> VPN((VPN Exit))
```

</center>

A two-way killswitch protects your privacy:

1. **NetworkPolicy**: Kubernetes blocks traffic if the Gluetun pod dies
2. **Gluetun's internal firewall**: Blocks traffic if the VPN connection drops

See [Networking](../security/network.md) for technical details on how the killswitch works.

This means:

- A single VPN connection serves all connected charms
- Charms don't need individual VPN configurations
- Your real IP is never exposed to torrent trackers, indexers, or usenet providers in a resilient and reliable way

The Gluetun charm enables bootstrapping this fairly advanced networking layer with a simple intuitive command:

```bash
juju integrate gluetun sabnzbd
```

### Lifecycle

```mermaid
sequenceDiagram
    participant GC as Gluetun Charm
    participant Gluetun as Gluetun App
    participant CC as Connected Charms

    GC->>GC: Read VPN credentials from Juju secret
    GC->>GC: Bootstrap pod-gateway server
    GC->>Gluetun: Start
    Gluetun-->>GC: VPN connected
    Note over GC: Waits if no reply

    CC-->>GC: I need VPN routing
    GC-->>CC: Here's the gateway info
    CC->>CC: Bootstrap pod-gateway client
    CC->>GC: Connect via VXLAN
    CC->>Gluetun: Route traffic through VPN
```

### Configuration

The charm requires:

- **VPN provider** (e.g., mullvad, protonvpn, custom)
- **WireGuard private key** stored as a Juju secret
- **Cluster CIDRs** so internal traffic bypasses the VPN

See [gluetun-k8s on Charmhub](https://charmhub.io/gluetun-k8s) for all options.

### Actions

#### `speedtest`

Measure throughput through the active VPN tunnel using a bundled [librespeed-cli](https://github.com/librespeed/speedtest-cli) binary. The test runs inside the gluetun container, so all traffic traverses the VPN — useful for verifying the link or comparing servers.

```bash
juju run gluetun-k8s/0 speedtest --wait=3m
```

A typical run takes about 60 seconds (download phase + upload phase + setup), so set `--wait` to at least `2m`.

**Parameters:**

| Param       | Type | Default | Description                                                            |
|-------------|------|---------|------------------------------------------------------------------------|
| `server-id` | int  | _auto_  | Pin a specific [LibreSpeed server ID](https://librespeed.org/) — by default the closest server is auto-selected. |
| `duration`  | int  | `15`    | Per-direction test duration in seconds.                                |
| `timeout`   | int  | `30`    | HTTP request timeout in seconds.                                       |

**Result keys:**

- `download-mbps`, `upload-mbps` — throughput in megabits/sec
- `ping-ms`, `jitter-ms` — latency to the test server
- `bytes-sent`, `bytes-received` — raw byte counts
- `server-name`, `server-url` — the server that was selected

The action fails if the unit is not the leader, the charm is misconfigured, or the VPN is not connected (the kill switch would block the test anyway).
