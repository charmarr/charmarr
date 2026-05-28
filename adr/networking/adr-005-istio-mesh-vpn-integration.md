# Istio Ambient Mesh Integration Strategy

**Status:** Accepted

## Context and Problem Statement

Charmarr uses Istio Ambient mesh for mTLS and observability between arr services. Download clients need to communicate with arr services (Radarr tells qBittorrent to download) while also routing external traffic through VPN. How do we integrate VXLAN-based VPN routing with Istio Ambient mesh without conflicts?

Related: See [Networking ADR-001](adr-001-ingress.md) for Istio gateway design.

## Considered Options

* **Download clients OUT of mesh** - Don't enroll download client namespace in Istio
* **Download clients IN mesh, gateway OUT** - Enroll clients, exclude gateway pod
* **Everything IN mesh** - Enroll both download clients and gateway
* **Use Istio egress gateway instead of VXLAN** - Rely entirely on Istio

## Decision Outcome

Chosen option: **"Download clients IN mesh, gateway OUT"**, because download clients benefit from Istio mTLS/observability when communicating with arr services, while the gateway pod operates below the mesh layer and must remain unenrolled. Routing table decisions happen before ztunnel interception, enabling VXLAN and mesh traffic to coexist.

```mermaid
graph LR
    subgraph "charmarr-downloads namespace (mesh enrolled)"
        DC[qBittorrent<br/>IN mesh]
    end

    subgraph "gluetun namespace (NOT mesh enrolled)"
        GW[gluetun gateway<br/>OUT of mesh]
    end

    subgraph "charmarr-core namespace (mesh enrolled)"
        ARR[Radarr<br/>IN mesh]
    end

    DC -->|dst: Radarr service IP<br/>via eth0| Z1[ztunnel]
    Z1 -->|mTLS| Z2[ztunnel]
    Z2 --> ARR

    DC -->|dst: tracker IP<br/>via vxlan0| GW
    GW -->|tun0| VPN[VPN tunnel]

    style DC fill:#e3f2fd
    style ARR fill:#e3f2fd
    style GW fill:#fff3e0
    style Z1 fill:#f3e5f5
    style Z2 fill:#f3e5f5
```

### Why This Works: Layer Separation

The key insight is that **routing table decisions happen before ztunnel interception**.

When qBittorrent sends a packet:

1. **Routing table consulted first** (Layer 3):
   - Destination matches cluster CIDR? → Send via eth0
   - Destination is external IP? → Send via vxlan0 (VXLAN route)

2. **ztunnel only sees eth0 traffic**:
   - Traffic via eth0 gets intercepted by ztunnel
   - Traffic via vxlan0 bypasses ztunnel entirely (different interface)

So internal traffic (qBittorrent → Radarr) goes through the mesh with mTLS, while external traffic (qBittorrent → tracker) goes through VXLAN to the VPN gateway, never touching ztunnel.

### Traffic Flow Details

**Internal traffic (qBittorrent → Radarr):**
1. Destination matches cluster service CIDR
2. Routing table: Send via eth0 (NOT vxlan0)
3. ztunnel intercepts (both pods in mesh)
4. mTLS encrypted, Istio telemetry captured
5. Result: Full mesh benefits

**External traffic (qBittorrent → tracker):**
1. Destination does NOT match cluster CIDR
2. Routing table: Send via vxlan0 interface (pod-gateway client configured this)
3. VXLAN encapsulation to gateway pod
4. ztunnel never sees this traffic (different interface)
5. Gateway pod decapsulates, routes through gluetun's tun0
6. Traffic exits via VPN tunnel
7. Result: VPN routing without mesh interference

### Namespace Enrollment

| Namespace | Mesh Enrolled | Reason |
|-----------|--------------|--------|
| charmarr-core | ✅ Yes | Radarr, Sonarr, Prowlarr, Overseerr, Plex need mTLS |
| charmarr-downloads | ✅ Yes | qBittorrent, SABnzbd need mTLS for arr communication |
| gluetun (separate) | ❌ No | Gateway pod must not have ztunnel interference |

**Critical**: The gluetun-k8s charm should deploy to a namespace that is NOT labeled for mesh enrollment. This is the user's responsibility to configure correctly.

### Consequences

* Good, because download clients get mTLS for arr ↔ client communication
* Good, because Istio observability shows download client traffic to arr services
* Good, because VXLAN traffic bypasses ztunnel (different interface), no conflict
* Good, because routing decision happens before ztunnel interception (clean separation)
* Good, because gateway pod outside mesh keeps VPN routing simple (no sidecar/ztunnel interference)
* Bad, because requires user to ensure gluetun namespace is NOT labeled for mesh enrollment
* Bad, because two namespaces with different enrollment states (operational complexity)

### Why NOT Istio Egress Gateway

Istio egress gateway operates at Layer 7 (HTTP) or Layer 4 (TCP with SNI). It's designed for:
- Controlling which external services mesh workloads can access
- Adding mTLS to external connections
- Traffic shaping for specific destinations

It does NOT work for:
- BitTorrent protocol (not HTTP, random peer IPs)
- "Route ALL external traffic through VPN" use case
- UDP traffic (common in torrents)

The VXLAN approach operates at Layer 3 (IP routing), which is the correct layer for "send all non-cluster traffic somewhere else."

### Configuration Requirements

**gluetun-k8s namespace:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: gluetun
  # NO istio.io/dataplane-mode label
```

**charmarr-downloads namespace:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: charmarr-downloads
  labels:
    istio.io/dataplane-mode: ambient  # Enrolled in mesh
```

### Cross-Namespace Communication

Download clients (charmarr-downloads) relate to gluetun (gluetun namespace) via Juju cross-model relations. The VXLAN tunnel crosses namespace boundaries at the IP level - this works because VXLAN is encapsulated UDP traffic to a specific pod IP, which Kubernetes networking allows regardless of namespace.

### Critical: ztunnel Link-Local Address Routing

**Problem discovered (2024-12-24):** When pods are enrolled in Istio ambient mesh AND have VPN routing configured, kubelet probes fail with timeout errors, causing CrashLoopBackOff.

**Root cause:** Istio ambient mode uses a hardcoded link-local address `169.254.7.127` for ztunnel ↔ pod communication. When ztunnel proxies traffic to a pod:

1. ztunnel connects to pod from source IP `169.254.7.127`
2. Pod receives request and sends TCP SYN-ACK response
3. Response is routed via pod's routing table
4. **With VPN routing:** Default route is `vxlan0 → gluetun`, so response goes to VPN gateway
5. Response never reaches ztunnel → TCP handshake fails → probe timeout

```
# Observed in pod with VPN routing + Istio ambient:
$ ss -tn | grep 38812
SYN_RECV  [::ffff:10.1.239.103]:38812 [::ffff:169.254.7.127]:49496
# Connections stuck in SYN_RECV - SYN-ACK going to wrong destination
```

**Solution:** The `NOT_ROUTED_TO_GATEWAY_CIDRS` must include `169.254.7.127/32` (ztunnel's specific link-local address) so responses to ztunnel route via eth0, not vxlan0.

```
# Required routing table entries for Istio ambient + VPN:
default via 172.16.0.1 dev vxlan0              # External → VPN
10.1.0.0/16 via 169.254.1.1 dev eth0          # Pod network → eth0
10.152.183.0/24 via 169.254.1.1 dev eth0      # Service network → eth0
169.254.7.127 via 169.254.1.1 dev eth0        # ztunnel link-local → eth0 ← CRITICAL
```

**Why 169.254.7.127?** Istio ambient mode uses SNAT to rewrite kubelet probe traffic with this link-local address, allowing it to bypass ztunnel authorization. This is documented in:

- [Istio: Ztunnel traffic redirection](https://istio.io/latest/docs/ambient/architecture/traffic-redirection/) - Architecture overview of how ztunnel intercepts traffic
- [Istio: Troubleshoot connectivity issues with ztunnel](https://istio.io/latest/docs/ambient/usage/troubleshoot-ztunnel/) - Debugging ztunnel issues
- [Istio: Ambient and Kubernetes NetworkPolicy](https://istio.io/latest/docs/ambient/usage/networkpolicy/) - Interaction between NetworkPolicy and ambient mode
- [Istio CNI iptables source](https://github.com/istio/istio/blob/master/cni/pkg/iptables/iptables.go) - Source code where 169.254.7.127 is defined

The address `169.254.7.127` is a hardcoded constant in Istio's CNI, stable across deployments.

**Implementation:** charmarr-lib automatically includes `169.254.7.127/32` in:
- `NOT_ROUTED_TO_GATEWAY_CIDRS` (pod-gateway client routing)
- Kill switch NetworkPolicy egress rules

This is the specific address Istio uses and is safe because link-local addresses are non-routable by IETF standard (RFC 3927).
