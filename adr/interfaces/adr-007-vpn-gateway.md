# VPN Gateway Interfac# VPN Gateway Interface

**Status:** Accepted

## Context and Problem Statement

Download clients (qBittorrent, SABnzbd) need to route their traffic through a VPN gateway (gluetun-k8s) via VXLAN overlay networking. Both the gateway charm and consumer charms need to be patched with pod-gateway containers at runtime. This interface must enable clean integration while following Juju's relation-based orchestration model and allowing future extensibility for alternative routing methods.

## Considered Options

* Active provider + active requirer pattern (both sides react)
* Passive provider + active requirer pattern (provider publishes, requirer reacts)
* Hardcoded routing method (pod-gateway only)
* Configurable routing method via relation data (extensible)

## Decision Outcome

Chosen option: **"Passive provider + active requirer with configurable routing method"**, because:

1. **Passive provider pattern**: The VPN gateway publishes configuration and doesn't need to track individual consumers. This matches the pattern used for other Charmarr interfaces.

2. **Active requirer pattern**: Download clients react when gateway config changes to patch their StatefulSets and create NetworkPolicy.

3. **Configurable routing method**: The provider specifies `routing_method` in relation data (defaulting to `pod-gateway`). The requirer reads this and applies the appropriate patching strategy. This allows future routing methods without charm code changes - only library updates needed.

### Library Structure

The `vpn-gateway` interface is implemented in **charmarr-vpn**, a package within the charmarr-lib monorepo. This design:

* Provides consistent packaging with other Charmarr libraries (charmarr-core, charmarr-testing)
* Allows gluetun-k8s charm (or future alternatives) to implement the provider side
* Enables any charm needing VPN egress to use the requirer side
* Maintains clean separation of VPN functionality from core interfaces
* Still allows reuse beyond the Charmarr ecosystem

**charmarr-vpn provides:**

* `VPNGatewayProvider` - for VPN gateway charms
  - Patches gateway charm's StatefulSet with pod-gateway gateway containers
  - Publishes routing config and method to relation data
  - Handles gateway-side VXLAN setup

* `VPNGatewayRequirer` - for consumer charms
  - Reads `routing_method` from relation data
  - Patches consumer's StatefulSet with appropriate client containers
  - Creates NetworkPolicy for kill switch
  - Provides `reconcile()` method that handles everything

* Data models (`VPNGatewayProviderData`, `VPNGatewayRequirerData`)

* Constants (pod-gateway image version, VXLAN defaults)

### Extensibility Model

```python
# Current usage (gluetun-k8s)
self.gateway = VPNGatewayProvider(self, "vpn-gateway")
# Defaults to routing_method="pod-gateway"

# Future hypothetical usage
self.gateway = VPNGatewayProvider(self, "vpn-gateway", routing_method="ebpf-routing")
```

Consumer charms don't specify routing method - they just call `reconcile()` and the library handles it based on what the provider advertised:

```python
# Consumer charm (unchanged regardless of routing method)
self.vpn = VPNGatewayRequirer(self, "vpn-gateway")

def _reconcile(self, event):
    if self.vpn.is_ready():
        self.vpn.reconcile()  # Library checks routing_method internally
```

To add a new routing method:
1. Update charmarr-vpn with new patching logic
2. Consumer charms automatically support it after lib update
3. Optionally update provider charms to use new method

### Consequences

* Good, because follows established Charmarr interface patterns (passive provider)
* Good, because routing method communicated via relation data (extensible)
* Good, because consumer charms don't need to know routing details
* Good, because adding new routing methods doesn't require consumer charm changes
* Good, because VPN gateway complexity isolated from download clients
* Good, because single `changed` event enables clean reconciler pattern
* Good, because `external_ip` enables user verification of VPN functionality
* Good, because topology visible via `juju status --relations`
* Good, because charmarr-vpn is reusable beyond Charmarr
* Bad, because download clients need lightkube for StatefulSet patching (via charmarr-vpn)
* Bad, because download clients need RBAC permissions to patch their own StatefulSets

## Interface Data Models

### Provider Data (Published by gluetun-k8s)

```python
from typing import Optional
from pydantic import BaseModel, Field

class VPNGatewayProviderData(BaseModel):
    """Data published by VPN gateway provider."""

    # Routing method - tells requirer how to configure itself
    routing_method: str = Field(
        default="pod-gateway",
        description="Routing method: 'pod-gateway' (VXLAN overlay)"
    )

    # VXLAN routing configuration (used when routing_method="pod-gateway")
    vxlan_id: int = Field(
        description="VXLAN ID for overlay network, e.g., 42"
    )
    vxlan_gateway_ip: str = Field(
        description="Gateway IP address in VXLAN subnet, e.g., '172.16.0.1'"
    )
    cluster_cidrs: str = Field(
        description="Comma-separated CIDRs to NOT route through VPN, e.g., '10.42.0.0/16,10.96.0.0/12'"
    )

    # Gateway health
    vpn_connected: bool = Field(
        description="Whether VPN tunnel is established and healthy"
    )

    # Verification/debugging
    external_ip: Optional[str] = Field(
        default=None,
        description="Current VPN exit IP address for user verification"
    )

    # Identity
    instance_name: str = Field(
        description="Juju application name, e.g., 'gluetun'"
    )
```

### Requirer Data (Published by Download Clients)

```python
from charmarr_lib.interfaces.download_client import DownloadClient

class VPNGatewayRequirerData(BaseModel):
    """Data published by VPN gateway requirers (download clients)."""

    client: DownloadClient = Field(
        description="Download client type (qbittorrent, sabnzbd, etc.)"
    )
    instance_name: str = Field(
        description="Unique identifier, e.g., 'qbittorrent-vpn'"
    )
```

## Relation Schema (metadata.yaml)

**gluetun-k8s:**
```yaml
provides:
  vpn-gateway:
    interface: vpn-gateway
```

**qbittorrent-k8s, sabnzbd-k8s:**
```yaml
requires:
  vpn-gateway:
    interface: vpn-gateway
    limit: 1  # Only one VPN gateway per download client
```

## Provider-Side Patching

The `VPNGatewayProvider` class patches the gateway charm's own StatefulSet to add pod-gateway containers:

```python
class VPNGatewayProvider:
    def __init__(self, charm, relation_name, routing_method="pod-gateway"):
        self._routing_method = routing_method
        # ...
    
    def reconcile(self):
        """Patch gateway StatefulSet and publish relation data."""
        if self._routing_method == "pod-gateway":
            self._patch_gateway_containers()
        
        self._publish_provider_data()
```

This means gluetun-k8s charm only declares the gluetun container in charmcraft.yaml. The pod-gateway gateway containers are added at runtime by the library.

## User Workflow

```bash
# Deploy VPN gateway
juju deploy gluetun-k8s gluetun --trust \
    --config vpn-provider=nordvpn \
    --config wireguard-private-key=secret:vpn-creds

# Deploy download client
juju deploy qbittorrent-k8s qbittorrent --trust

# Relate to enable VPN routing
juju relate qbittorrent:vpn-gateway gluetun:vpn-gateway

# Check status
juju status
# gluetun/0: active - VPN connected: Switzerland (185.112.34.56)
# qbittorrent/0: active - Routing via gluetun (185.112.34.56)

# Verify VPN routing is working
kubectl exec -it qbittorrent-0 -- curl ifconfig.me
# Should show VPN exit IP
```

## charmarr-vpn Implementation Notes (Validated 2025-12-11)

### Provider-Side Patching (VPNGatewayProvider)

The library's `VPNGatewayProvider.reconcile()` method must:

1. **Patch gateway StatefulSet** with pod-gateway gateway containers:
   - Init container with **privileged: true** and **iptables fix**
   - Sidecar container (only needs NET_ADMIN capability)

2. **Discover cluster CIDRs** automatically:
   ```python
   # Query cluster-info dump for pod and service CIDRs
   pod_cidr = self._get_pod_cidr()
   service_cidr = self._get_service_cidr()
   ```

3. **Publish provider data** including:
   - `cluster_cidrs`: **Comma-separated string** in relation data (e.g., `"10.1.0.0/16,10.152.183.0/24"`)
   - `vpn_connected`: Query gluetun's /v1/publicip/ip endpoint
   - `external_ip`: For user verification

### Requirer-Side Patching (VPNGatewayRequirer)

The library's `VPNGatewayRequirer.reconcile()` method must:

1. **Check gateway readiness** before patching:
   ```python
   if not provider_data.vpn_connected:
       # Set WaitingStatus, don't patch yet
       return
   ```

2. **Create ConfigMap** with cluster CIDRs and DNS IP:
   ```python
   dns_ip = self._get_dns_service_ip()  # Query kube-dns/coredns service

   # CRITICAL: Convert comma-separated (relation data) to space-separated (ConfigMap)
   # Client scripts use shell word splitting on spaces
   cluster_cidrs_spaces = provider_data.cluster_cidrs.replace(',', ' ')

   configmap_data = {
       "settings.sh": f"""K8S_DNS_IPS="{dns_ip}"
NOT_ROUTED_TO_GATEWAY_CIDRS="{cluster_cidrs_spaces}"
"""
   }
   ```

3. **Patch consumer StatefulSet** with:
   - Init container (NET_ADMIN capability)
   - Sidecar container (NET_ADMIN capability)
   - ConfigMap volume mount

4. **Create NetworkPolicy** kill switch

5. **Monitor relation changes** and unpatch when relation breaks

### Validation Results

**Architecture validated on MicroK8s with Calico CNI:**
- ✅ Cross-namespace VXLAN routing (gateway and client in different namespaces)
- ✅ Kill switch blocks traffic when VPN down
- ✅ Auto-recovery after gateway restart (~10 seconds)
- ✅ Cluster traffic preserved (DNS, pod-to-pod, services)
- ✅ Resource overhead: ~3MB RAM per client sidecar

## Related ADRs

- **ADR-002: VPN Gateway Solution** - Defines gluetun + pod-gateway architecture
- **ADR-003: Download Client VPN Integration** - Defines consumer self-patching approach
- **ADR-004: VPN Kill Switch** - Defines two-layer kill switch with consumer-owned NetworkPolicy
- **ADR-005: Istio Mesh Integration** - Download clients IN mesh, gateway OUT
