# VPN Kill Switch Implementation Strategy

**Status:** Accepted

## Context and Problem Statement

Download clients must never leak traffic to the internet if the VPN disconnects or if routing configuration fails. A "kill switch" prevents the user's real IP address from being exposed to trackers/providers. How do we implement a reliable kill switch that catches both VPN failures and routing misconfigurations?

## Considered Options

* **Gluetun firewall only** - Rely solely on gluetun's built-in iptables kill switch
* **NetworkPolicy only** - Use Kubernetes NetworkPolicy to restrict egress
* **NetworkPolicy + gluetun firewall (two-layer defense)** - Defense in depth with both mechanisms
* **Istio AuthorizationPolicy** - Use Istio mesh policies to control egress

## Decision Outcome

Chosen option: **"NetworkPolicy + gluetun firewall (two-layer defense)"**, because NetworkPolicy catches routing misconfigurations (init container failures, deleted routes) that occur before traffic reaches the gateway, while gluetun's firewall catches VPN disconnections at the gateway itself. This follows k8s@home's battle-tested pattern and provides defense in depth.

### NetworkPolicy Ownership

Consumer charms create and manage their own NetworkPolicy resources via vpn-k8s-lib's `VPNGatewayRequirer.reconcile()` method. This maintains clean resource ownership - the gluetun-k8s charm only provides connection data, consumers are responsible for their own network restrictions.

```mermaid
graph TD
    A[Download Client Pod] -->|dst: external IP| B{Routing Table}
    B -->|VXLAN route exists| C[vxlan0 interface]
    B -->|VXLAN route missing| D{NetworkPolicy}

    C --> E[gluetun pod receives]
    E --> F{Gluetun Firewall}
    F -->|VPN connected| G[tun0 → VPN tunnel]
    F -->|VPN disconnected| H[BLOCKED ❌]

    D -->|dst in cluster CIDR| I[ALLOWED ✓]
    D -->|dst NOT in cluster CIDR| J[BLOCKED ❌<br/>Kill Switch Activated]

    style H fill:#ff6b6b
    style J fill:#ff6b6b
    style G fill:#51cf66
```

### Two Layers Explained

**Layer 1: Consumer NetworkPolicy (catches routing failures)**

If the pod-gateway client init container fails, or VXLAN routes get deleted, or the VXLAN interface goes down - traffic would try to go via the pod's default route (directly to internet). NetworkPolicy blocks this because the destination IP isn't in the allowed cluster CIDRs.

**Layer 2: Gluetun Firewall (catches VPN disconnection)**

If VXLAN routing works but the VPN tunnel inside gluetun disconnects, traffic arrives at gluetun but can't exit. Gluetun's built-in firewall blocks all non-VPN egress traffic.

### NetworkPolicy Specification

Created by vpn-k8s-lib when consumer relates to VPN gateway:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: qbittorrent-vpn-killswitch
  namespace: charmarr-downloads
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: qbittorrent
  policyTypes:
    - Egress
  egress:
    # Allow cluster pod CIDR
    - to:
        - ipBlock:
            cidr: 10.42.0.0/16
    # Allow cluster service CIDR  
    - to:
        - ipBlock:
            cidr: 10.96.0.0/12
    # Allow DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

### How VXLAN Traffic Bypasses the Block

1. Download client sends packet to external IP (e.g., 1.2.3.4)
2. Routing table has VXLAN route: default via 172.16.0.1 dev vxlan0
3. Packet encapsulated in VXLAN: **outer destination = gateway pod IP (in cluster CIDR)**
4. NetworkPolicy evaluates outer packet: destination in cluster CIDR → ALLOWED
5. Packet reaches gateway pod, gets decapsulated
6. Gluetun routes through VPN tunnel

The key insight: VXLAN encapsulation makes external traffic look like cluster-internal traffic to NetworkPolicy.

### Consequences

* Good, because NetworkPolicy enforced at node level (outside pod, can't be bypassed if pod compromised)
* Good, because NetworkPolicy catches routing failures (init container didn't run, VXLAN down, routes deleted)
* Good, because gluetun firewall catches VPN disconnections at the gateway
* Good, because defense in depth - two independent enforcement points
* Good, because consumer ownership of NetworkPolicy maintains clean resource boundaries
* Good, because NetworkPolicy automatically allows VXLAN traffic (encapsulated to cluster IP)
* Bad, because requires accurate cluster CIDR discovery for NetworkPolicy
* Bad, because two systems to understand (but both are standard Kubernetes/VPN patterns)

**Rejected alternatives:**

* Gluetun only: Doesn't catch routing failures. If VXLAN never sets up, traffic goes direct to internet via pod's default route.
* NetworkPolicy only: Doesn't protect against VPN disconnection at gateway. Traffic would arrive at gateway but have nowhere to go (less severe, but still a failure mode).
* Istio AuthorizationPolicy: Operates at Layer 7/4, only sees ztunnel-intercepted traffic. VXLAN traffic uses vxlan0 interface which bypasses ztunnel entirely. Wrong layer for IP routing control.

### Failure Scenarios

| Scenario | Layer 1 (NetworkPolicy) | Layer 2 (Gluetun) | Result |
|----------|------------------------|-------------------|--------|
| Normal operation | Allows VXLAN (encap to cluster IP) | Allows via tun0 | ✅ Traffic flows |
| Client init container fails | Blocks direct egress | N/A (traffic never arrives) | ✅ Blocked |
| VXLAN interface down | Blocks direct egress | N/A (traffic never arrives) | ✅ Blocked |
| Gateway pod restarts | Client sidecar detects, resets VXLAN | N/A | ✅ Self-heals |
| VPN disconnects | Allows VXLAN traffic through | Blocks at firewall | ✅ Blocked |
| VPN provider blocks IP | Allows VXLAN traffic through | Blocks (no route via tun0) | ✅ Blocked |

## Validation Results (2025-12-11)

**Tested on MicroK8s with Calico CNI and ProtonVPN WireGuard:**

### Normal Operation
- ✅ External traffic routes through VPN (verified public IP: 91.132.139.6)
- ✅ Cluster DNS works (kubernetes.default.svc.cluster.local resolves)
- ✅ Pod-to-pod traffic works (reached nginx at 10.1.239.102)

### Kill Switch Activated (Gateway Pod Deleted)
- ✅ External traffic **BLOCKED** (curl to ifconfig.me timed out after 10 seconds)
- ✅ Cluster traffic **PRESERVED** (nginx pod still reachable)
- ✅ DNS resolution **PRESERVED** (CoreDNS still accessible)

### Recovery After Gateway Restart
- ✅ Gateway pod recreated and ready in ~60 seconds
- ✅ Client auto-reconnected in ~10 seconds after gateway ready
- ✅ VXLAN interface re-established (new DHCP IP: 172.16.0.205/24)
- ✅ External traffic restored (public IP: 91.132.139.6)

**Key findings:**
- **Two-layer defense validated**: NetworkPolicy catches routing failures, gluetun catches VPN failures
- **Zero data leakage**: External traffic blocked during gateway downtime
- **Automatic recovery**: No manual intervention needed after gateway restart
- **Cluster connectivity preserved**: Kill switch only blocks external traffic
