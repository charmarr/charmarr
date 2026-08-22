# Networking

Charmarr secures network traffic at multiple [OSI layers](https://en.wikipedia.org/wiki/OSI_model). Each layer addresses a different concern, and together they provide defense in depth.

| Layer | Technology | Purpose | Applies |
|-------|------------|---------|---------|
| **L2** | VXLAN overlay | External traffic anonymization through VPN | Always |
| **L7** | Ingress gateway | External client ingress and routing | Always |
| **L4** | Istio ztunnel | Internal encrypted transport, L4 authorization | With Istio |
| **L4/L7** | Istio waypoint | Internal L4/L7 authorization | With Istio |

Charmarr can be deployed with Istio, which adds the L4 and L4/L7 layers and replaces the L7 gateway with Istio's own. Without it you get Traefik at L7 and the VPN overlay at L2, and internal pod-to-pod traffic is plain and unrestricted, which is the normal Kubernetes default. See [Enabling Istio](#enabling-istio).

## L2: VXLAN Overlay

Privacy-sensitive charms (qBittorrent, SABnzbd, Prowlarr) must not expose your home IP to external services. Charmarr solves this with a VXLAN overlay network that tunnels external traffic through a VPN.

Each privacy-sensitive pod runs a pod-gateway client. This client establishes a VXLAN tunnel to a pod-gateway server running on the Gluetun pod. All external traffic from the pod routes through this tunnel, into the Gluetun pod, and the [gluetun](https://github.com/qdm12/gluetun) container routes this traffic out through a WireGuard VPN connection.

<center>

```mermaid
flowchart LR
    subgraph Source Pod
        SrcPod[Source Pod]
        PGC[Pod Gateway Client]
    end

    subgraph Gluetun Pod
        PGS[Pod Gateway Server]
        subgraph Gluetun App
            WG[WireGuard]
        end
    end

    SrcPod -->|External| PGC
    PGC -->|VXLAN| PGS
    PGS --> WG
    WG -->|Outbound| Internet((Internet))
```

</center>

The VXLAN overlay only captures traffic destined for external networks. Intra-cluster traffic bypasses the overlay entirely and flows through the higher layers (L4/L7) unaffected. This is configured via cluster CIDRs that tell the pod-gateway client which destinations are internal.

A two-way killswitch protects against VPN failures:

1. **Gluetun firewall**: Blocks traffic if the WireGuard connection drops
2. **NetworkPolicy**: Kubernetes blocks traffic if the Gluetun pod dies

Here's an example NetworkPolicy that Charmarr creates for SABnzbd:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sabnzbd-k8s-vpn-killswitch
  namespace: charmarr
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: sabnzbd-k8s
  policyTypes:
  - Egress
  egress:
  - to:
    - ipBlock:
        cidr: 10.1.0.0/16       # Pod CIDR
  - to:
    - ipBlock:
        cidr: 10.152.183.0/24   # Service CIDR
  - to:
    - ipBlock:
        cidr: 192.168.0.0/24    # LAN CIDR
  - to:
    - ipBlock:
        cidr: 169.254.7.127/32  # Pod-gateway server IP
  - ports:
    - port: 53
      protocol: UDP
    - port: 53
      protocol: TCP
    to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
```

This policy only allows SABnzbd to send traffic to:

- **Cluster CIDRs** (pod, service, LAN): Internal traffic that bypasses the VPN
- **Pod-gateway server IP**: The entry point into the VXLAN tunnel on the Gluetun pod
- **kube-system DNS**: Required for name resolution

All other egress is blocked. If the Gluetun pod dies, the pod-gateway server becomes unreachable and SABnzbd cannot reach the internet.

See [VPN Gateway](../charms/vpn-gateway.md) for how the `gluetun-k8s` charm works.

## L4/L7: Service Mesh

East-west traffic (intra-cluster) flows through [Istio ambient mesh](https://istio.io/latest/docs/ambient/overview/). Unlike the VXLAN layer which anonymizes north-south traffic (external), the service mesh encrypts and authorizes internal pod-to-pod communication.

Charmarr uses the [Charmed Istio](https://canonical-service-mesh-documentation.readthedocs-hosted.com/en/latest/) distribution (which I co-maintain for Canonical, shameless plug). The charmed service mesh automatically enrolls Charmarr pods into the mesh and configures authorization policies based on charm topology and policies defined in charm code.

### Enabling Istio

Istio is off by default. Turning it on is one flag, but the control plane is yours to run: Charmarr deploys `istio-ingress-k8s` and `istio-beacon-k8s`, never `istio-k8s` itself.

**1. Check your cluster can take it**

- [x] No Istiod already running on the cluster (if you don't know, it's probably not)
- [x] Not using K3s or k3d (read the warning below)
- [x] Not using Cilium CNI (or willing to [configure it](https://istio.io/latest/docs/ambient/install/platform-prerequisites/#cilium))
- [x] LoadBalancer has an address free for each ingress gateway

Not all checked? Stay on Traefik. See [Istio platform prerequisites](https://istio.io/latest/docs/ambient/install/platform-prerequisites/) for details.

!!! warning
    K3s and k3d use non-standard CNI paths that can conflict with Istio Ambient. Adding Istio may disrupt the CNI chain and cause hard-to-debug networking issues. It can work with careful configuration: [K3s docs](https://istio.io/latest/docs/ambient/install/platform-prerequisites/#k3s), [k3d docs](https://istio.io/latest/docs/ambient/install/platform-prerequisites/#k3d). So if you want to use it with Istio Ambient, do it at your own discretion.

**2. Deploy the control plane**

```bash
juju add-model istio-system
juju deploy istio-k8s --channel=dev/edge --trust
```

!!! note "Pick your channel"
    `dev/edge` tracks the in-development release. Check [canonical/service-mesh](https://github.com/canonical/service-mesh) for the current stable track and use that instead if one suits you better.

**3. Switch Charmarr over**

With Terraform, set the flag:

```hcl
module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  # ... your other config ...

  enable_istio = true
  istio_channel = "dev/edge"  # match your control plane
}
```

This swaps every Traefik gateway for an Istio one and enrolls every application in the mesh. There is no halfway setting. `istio_channel` applies to every Istio charm Charmarr deploys, and should match the track you used for `istio-k8s`.

!!! note
    Terraform reads the cluster to confirm the control plane is there before it changes anything, so it needs a working kubeconfig at `~/.kube/config` (or `KUBE_CONFIG_PATH` pointing at one). If the control plane is missing, the plan fails saying so. Staying on Traefik needs no kubeconfig at all.

Each application also takes an `ingress_path` and `ingress_port`. Traefik owns its own routing, so those values only take effect here.

#### Manual Deployment

If you followed [Manual Deploy](../setup/manual.md) instead, swap the Traefik gateways for Istio ones and add the beacon yourself.

```bash
juju deploy istio-ingress-k8s --trust --channel=dev/edge arr-ingress
juju deploy istio-ingress-k8s --trust --channel=dev/edge plex-ingress
juju deploy istio-ingress-k8s --trust --channel=dev/edge seerr-ingress
juju deploy istio-beacon-k8s --trust --channel=dev/edge beacon
```

Route each application through its gateway over `istio-ingress-route` instead of `ingress`:

```bash
juju integrate radarr:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate sonarr:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate prowlarr:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate qbittorrent:istio-ingress-route arr-ingress:istio-ingress-route
juju integrate sabnzbd:istio-ingress-route arr-ingress:istio-ingress-route

juju integrate plex:istio-ingress-route plex-ingress:istio-ingress-route
juju integrate seerr:istio-ingress-route seerr-ingress:istio-ingress-route
```

Enroll every application in the mesh:

```bash
juju integrate radarr:service-mesh beacon:service-mesh
juju integrate sonarr:service-mesh beacon:service-mesh
juju integrate prowlarr:service-mesh beacon:service-mesh
juju integrate qbittorrent:service-mesh beacon:service-mesh
juju integrate sabnzbd:service-mesh beacon:service-mesh
juju integrate plex:service-mesh beacon:service-mesh
juju integrate seerr:service-mesh beacon:service-mesh
```

Under Istio the routing is yours to set, via `ingress-path` and `ingress-port`. Each defaults to the application name and port 80, so apps sharing a gateway already land on distinct prefixes. Override when you want something else:

```bash
juju config radarr ingress-path=/movies
juju config radarr ingress-port=8080
```

These two settings do nothing over the generic `ingress` relation, where Traefik owns the path prefix.

### How Cluster Internal Traffic Flows

For details, refer to the [upstream Istio docs](https://istio.io/latest/docs/ambient/architecture/traffic-redirection/). TL;DR:

When a pod sends traffic to another pod (source and destination may be on the same node):

<center>

```mermaid
flowchart LR
    subgraph Source Node
        SrcPod[Source Pod]
        SrcZT[ztunnel]
    end

    WP[waypoint]

    subgraph Destination Node
        DstZT[ztunnel]
        DstPod[Destination Pod]
    end

    SrcPod -->|Plain| SrcZT
    SrcZT -->|HBONE| WP
    WP -->|HBONE| DstZT
    DstZT -->|Plain| DstPod
```

</center>

**Step 1: Source ztunnel (L4 firewall outlet)**

Traffic leaving a pod is redirected to the node's ztunnel. The ztunnel encrypts the traffic using the [HBONE protocol](https://istio.io/latest/docs/ambient/architecture/hbone/), which provides mTLS without the complexity of manually managing certificates. The ztunnel then forwards the encrypted traffic toward the destination.

**Step 2: Waypoint (L4/L7 firewall inlet)**

The encrypted traffic arrives at the waypoint proxy. The waypoint understands HBONE and can inspect traffic at both L4 and L7. It evaluates authorization policies (firewall rules) and only forwards traffic that matches an explicit allow rule. Traffic without a matching policy is dropped. The difference between ztunnel and waypoint policies is the target type. Understanding this distinction is out of scope for Charmarr docs, refer to the [upstream Istio documentation](https://istio.io/latest/docs/ambient/usage/l7-features/) for details.

**Step 3: Destination ztunnel (L4 firewall inlet)**

The waypoint forwards allowed traffic to the destination node's ztunnel. This ztunnel validates the traffic against its own L4 authorization policies. Traffic without a matching allow policy is dropped.

**Step 4: Delivery**

The destination ztunnel terminates the HBONE encryption and delivers the traffic to the destination pod as plaintext.

### Ingress

<center>

```mermaid
flowchart LR
    Client((Client))
    GW[Ingress Gateway]

    subgraph Destination Node
        DstZT[ztunnel]
        DstPod[Destination Pod]
    end

    Client -->|Inbound| GW
    GW -->|HBONE| DstZT
    DstZT -->|Plain| DstPod
```

</center>

External client traffic (e.g. a browser accessing Radarr) enters the cluster through the [Istio ingress gateway](https://istio.io/latest/docs/tasks/traffic-management/ingress/ingress-control/). The gateway evaluates routing rules and forwards traffic to the destination pod.

Traffic from the gateway is captured by the destination node's ztunnel for L4 processing, but the waypoint is bypassed. This is by design: the ingress gateway already operates at L7, so routing traffic through the waypoint would risk double-applying policies like traffic splitting or fault injection.

### Authorization Policies

The charmed service mesh automatically creates authorization rules based on the system topology and policy targets specified by charms. Unrelated pods cannot communicate.

This limits lateral movement if a pod is compromised. An attacker cannot reach pods that the compromised pod has no legitimate reason to contact.

## Traffic Isolation Architecture

Charmarr implements defense in depth through orthogonal network layers. The L2 VXLAN overlay handles north-south (external) traffic anonymization, the L4/L7 Istio ambient mesh secures east-west (internal) communication, and the Istio ingress gateway handles inbound client traffic. These layers operate independently with no shared failure modes.

External, internal, and inbound traffic take isolated paths:

<center>

```mermaid
flowchart LR
    subgraph Source Pod
        SrcPod[Source Pod]
        PGC[Pod Gateway Client]
    end

    subgraph Gluetun Pod
        PGS[Pod Gateway Server]
        subgraph Gluetun App
            WG[WireGuard]
        end
    end

    subgraph Istio Ambient
        SrcZT[ztunnel]
        WP[waypoint]
        DstZT[ztunnel]
        GW[Ingress Gateway]
    end

    Dst[Destination Pod]

    SrcPod -->|External| PGC
    PGC -->|VXLAN| PGS
    PGS --> WG
    WG -->|Outbound| Internet((Internet))

    SrcPod -->|Internal| SrcZT
    SrcZT -->|HBONE| WP
    WP -->|HBONE| DstZT
    DstZT -->|Plain| Dst

    Client((Client)) -->|Inbound| GW
    GW -->|HBONE| DstZT
```

</center>

This isolation ensures VPN failures don't cascade into internal operations or ingress. When the VPN connection drops or the Gluetun pod goes down, only north-south traffic is blocked. East-west communication and inbound client access remain fully functional. Radarr and Sonarr continue queuing requests to qBittorrent and SABnzbd, and users can still reach the web UIs. Once the VPN is restored, download clients resume fetching from the internet with no manual intervention.
