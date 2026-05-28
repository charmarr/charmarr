# VPN-K8S-Lib: Pod-Gateway Integration Library

**Status:** Accepted

## Context and Problem Statement

Charmarr's download clients (qBittorrent, SABnzbd) need to route external traffic through a VPN gateway for privacy. The chosen solution uses gluetun as the VPN client with pod-gateway for VXLAN overlay networking (see ADR-002). Both the gateway charm (gluetun-k8s) and consumer charms need to be patched with pod-gateway containers at runtime.

This ADR defines:
1. The vpn-k8s-lib library structure
2. Pod-gateway environment variable requirements for both gateway and client sides
3. Juju relation data models for the `vpn-gateway` interface
4. StatefulSet patching and NetworkPolicy implementation approach

## Considered Options

### Gateway Discovery Method
* **Option A: Pod IP in relation data** - Provider publishes pod IP directly, requirers use it
* **Option B: Service DNS name in relation data** - Provider publishes service FQDN, clients resolve via DNS

### Configuration Approach
* **Option A: All configurable** - Every pod-gateway setting exposed as charm config
* **Option B: Minimal configurable** - Only necessary settings configurable, rest hardcoded
* **Option C: Fully hardcoded** - No user configuration

### DNS IP Discovery
* **Option A: Query kube-dns Service via K8s API** - Provider queries and passes to clients
* **Option B: Auto-detect from /etc/resolv.conf** - Let pod-gateway scripts handle it

### Patching Approach
* **Option A: Raw dict construction** - Build patch dicts manually
* **Option B: Pydantic models with model_dump()** - Use typed models that serialize to K8s specs
* **Option C: Lightkube models directly** - Use lightkube's built-in model classes

### Config Model Design
* **Option A: Separate config models per use case** - GatewayContainerConfig, ClientContainerConfig, etc.
* **Option B: Reuse VPNGatewayProviderData directly** - Patching functions take the relation data model

### Patch Type
* **Option A: JSON Patch** - RFC 6902 operations (add, remove, replace)
* **Option B: Strategic Merge Patch** - K8s-native merge that handles lists intelligently
* **Option C: Server-Side Apply** - Declarative field management

## Decision Outcome

### Interface Decisions

**Gateway Discovery: Option B (Service DNS name)** - This is how pod-gateway is designed to work. The client init script resolves `GATEWAY_NAME` via cluster DNS. When gateway pod restarts, same DNS name resolves to new pod IP. Client sidecar detects connectivity loss and re-resolves.

**Configuration: Option B (Minimal configurable)** - Only `cluster-cidrs` (mandatory) and `vxlan-id` (optional, for multi-gateway deployments) are configurable. Everything else has sensible defaults that work for all deployments.

**DNS IP: Option B (Auto-detect)** - Pod-gateway's `client_init.sh` reads `K8S_DNS_IPS` from `/etc/resolv.conf` if not set. Kubelet injects the correct kube-dns ClusterIP into pod's resolv.conf. No need to pass this in relation data.

### Patching Decisions

**Patching Approach: Option B (Pydantic models)** - Provides type safety, validation, and clean serialization via `model_dump(by_alias=True, exclude_none=True)` for proper camelCase field names.

**Config Model Design: Option B (Reuse VPNGatewayProviderData)** - The relation data model already contains all fields needed for patching. No redundant config models except `KillSwitchConfig` which has different structure (app_name, namespace, cluster_cidrs as list).

**Patch Type: Option B (Strategic Merge Patch)** for StatefulSets - Adds containers without replacing Juju's existing containers. K8s merges lists by container name. **Option C (Server-Side Apply)** for NetworkPolicy - Idempotent create/update with field manager.

### Consequences

* Good, because minimal configuration - users only need to provide cluster CIDRs
* Good, because DNS-based gateway discovery handles pod restarts gracefully
* Good, because auto-detected K8S_DNS_IPS removes one potential misconfiguration
* Good, because multi-gateway supported via vxlan-id config
* Good, because hardcoded defaults work for all standard deployments
* Good, because type-safe container specs with Pydantic validation
* Good, because `model_dump(by_alias=True)` handles camelCase conversion automatically
* Good, because strategic merge patch coexists with Juju's container management
* Good, because reusing `VPNGatewayProviderData` eliminates redundant models
* Good, because server-side apply makes NetworkPolicy updates idempotent
* Good, because cleanup functions handle relation-broken gracefully
* Bad, because cluster-cidrs is mandatory - no auto-detection (but this is safer)
* Bad, because users must know their cluster CIDRs (documented for common distros)
* Bad, because Pydantic models duplicate some K8s API structures (but provides type safety)
* Bad, because strategic merge patch behavior depends on K8s version (but stable since 1.16)

## Library Structure

```
vpn-k8s-lib/
├── src/vpn_k8s_lib/
│   ├── __init__.py
│   ├── interfaces.py          # Data models + Provider/Requirer classes + Events
│   ├── constants.py           # Image versions, hardcoded defaults
│   └── patching/
│       ├── __init__.py
│       ├── models.py          # Pydantic models for K8s specs
│       ├── gateway.py         # Gateway StatefulSet patching
│       ├── client.py          # Client StatefulSet patching
│       └── network_policy.py  # Kill switch NetworkPolicy
```

## Pod-Gateway Environment Variables

### Gateway Side (gluetun-k8s)

These environment variables are set on the pod-gateway gateway containers patched into the gluetun-k8s StatefulSet:

| Env Var | Value | Source |
|---------|-------|--------|
| `VXLAN_ID` | `42` | Charm config (default: 42) |
| `VXLAN_IP_NETWORK` | `172.16.0` | Hardcoded |
| `VXLAN_GATEWAY_FIRST_DYNAMIC_IP` | `20` | Hardcoded |
| `VPN_INTERFACE` | `tun0` | Hardcoded (gluetun creates this) |
| `VPN_BLOCK_OTHER_TRAFFIC` | `true` | Hardcoded (kill switch) |
| `NOT_ROUTED_TO_GATEWAY_CIDRS` | e.g., `"10.42.0.0/16 10.43.0.0/16"` | Charm config (mandatory) |

### Client Side (qbittorrent-k8s, sabnzbd-k8s)

These environment variables are set on the pod-gateway client containers patched into consumer StatefulSets:

| Env Var | Value | Source |
|---------|-------|--------|
| `GATEWAY_NAME` | e.g., `"gluetun.gluetun.svc.cluster.local"` | Relation data |
| `VXLAN_ID` | `42` | Relation data |
| `VXLAN_IP_NETWORK` | `172.16.0` | Relation data |
| `NOT_ROUTED_TO_GATEWAY_CIDRS` | e.g., `"10.42.0.0/16 10.43.0.0/16"` | Relation data |

### Auto-Detected (Not Passed)

| Env Var | How Detected |
|---------|--------------|
| `K8S_DNS_IPS` | Client init reads from `/etc/resolv.conf` inside pod |

## Charm Configuration

### gluetun-k8s

```yaml
options:
  cluster-cidrs:
    type: string
    description: |
      Space-separated CIDRs for pod and service networks.
      Traffic to these CIDRs will NOT be routed through VPN.
      Example: "10.42.0.0/16 10.43.0.0/16" (k3s defaults)
               "10.1.0.0/16 10.152.183.0/24" (MicroK8s defaults)
      REQUIRED - charm will be blocked if not set.
    default: ""

  vxlan-id:
    type: int
    description: |
      VXLAN tunnel ID. Must be unique if deploying multiple VPN gateways.
      Range: 1-16777215
    default: 42
```

## Relation Data Models

### Provider Data (gluetun-k8s → consumers)

```python
class VPNGatewayProviderData(BaseModel):
    """Data published by VPN gateway provider on the relation."""

    gateway_dns_name: str  # Service FQDN for client DNS resolution
    vxlan_id: int = 42     # VXLAN tunnel ID
    vxlan_ip_network: str = "172.16.0"  # First 3 octets of VXLAN subnet
    cluster_cidrs: str     # Space-separated CIDRs to NOT route through VPN
    vpn_connected: bool = False  # Whether VPN tunnel is established
    external_ip: Optional[str] = None  # Current VPN exit IP for verification
```

**Field derivation in provider charm:**
- `gateway_dns_name`: `f"{self.app.name}.{self.model.name}.svc.cluster.local"`
- `cluster_cidrs`: From mandatory config
- `vxlan_id`: From config with default
- `vxlan_ip_network`: Hardcoded `"172.16.0"`
- `vpn_connected`: From gluetun health check
- `external_ip`: From gluetun API or ifconfig.me query

### Requirer Data (consumers → gluetun-k8s)

```python
class VPNGatewayRequirerData(BaseModel):
    """Data published by VPN gateway requirers (download clients)."""

    instance_name: str  # Client application name for logging/status
```

## Events Pattern

Following the established Charmarr interface pattern: **passive provider, active requirer**.

### Provider (No Custom Events)

The provider (gluetun-k8s) does not need custom events:
- Publishes data when workload is ready or config changes
- Does not need to react to requirers joining/leaving
- Data in relation databag is visible to all requirers automatically

### Requirer (Single `changed` Event)

```python
class VPNGatewayChangedEvent(EventBase):
    """Event emitted when VPN gateway relation data changes."""
    pass

class VPNGatewayRequirerEvents(ObjectEvents):
    """Events for VPNGatewayRequirer."""
    changed = EventSource(VPNGatewayChangedEvent)
```

**Internal event handling:**
- Library observes: `relation-changed`, `relation-broken`
- Library emits: Single `changed` event
- Charm observes: `self.vpn_gateway.on.changed` → triggers reconciler

## Interface Classes

### VPNGatewayProvider

```python
class VPNGatewayProvider(Object):
    """Provider side of vpn-gateway interface. Used by gluetun-k8s."""

    def __init__(self, charm: CharmBase, relation_name: str = "vpn-gateway")
    def publish_data(self, data: VPNGatewayProviderData) -> None
    def is_ready(self) -> bool
```

### VPNGatewayRequirer

```python
class VPNGatewayRequirer(Object):
    """Requirer side of vpn-gateway interface. Used by download clients."""

    on = VPNGatewayRequirerEvents()

    def __init__(self, charm: CharmBase, relation_name: str = "vpn-gateway")
    def publish_data(self, data: VPNGatewayRequirerData) -> None
    def get_gateway(self) -> Optional[VPNGatewayProviderData]
    def is_ready(self) -> bool
```

## Patching Implementation

### Container Patching (Strategic Merge Patch)

Both gateway and client StatefulSets are patched using strategic merge patch to add pod-gateway containers without replacing Juju's existing containers.

**Gateway containers (patched into gluetun-k8s):**
- `gateway-init`: Runs `gateway_init.sh`, privileged with NET_ADMIN + NET_RAW + SYS_MODULE
- `gateway-sidecar`: Runs `gateway_sidecar.sh`, privileged with NET_ADMIN + NET_RAW

**Client containers (patched into download clients):**
- `vpn-route-init`: Runs `client_init.sh`, privileged with NET_ADMIN
- `vpn-route-sidecar`: Runs `client_sidecar.sh`, unprivileged with NET_ADMIN capability

### NetworkPolicy (Server-Side Apply)

Kill switch NetworkPolicy is created using server-side apply with field manager `vpn-k8s-lib` for idempotent create/update.

**Policy specification:**
- Blocks all egress except cluster CIDRs and DNS
- Allows traffic to each cluster CIDR (pod + service)
- Allows DNS (UDP/TCP 53 to kube-system)
- VXLAN traffic passes because outer packet destination is within cluster CIDR

### Patching API

```python
# Gateway patching
def patch_gateway_statefulset(client, statefulset_name, namespace, data: VPNGatewayProviderData)

# Client patching
def patch_client_statefulset(client, statefulset_name, namespace, data: VPNGatewayProviderData)
def remove_client_containers(client, statefulset_name, namespace)

# NetworkPolicy
def create_killswitch_network_policy(client, config: KillSwitchConfig)
def delete_killswitch_network_policy(client, app_name, namespace)
```

**Note:** Patching functions take `VPNGatewayProviderData` directly - no separate config models needed. Only `KillSwitchConfig` exists because it has different structure (app_name, namespace, cluster_cidrs as list).

### Pydantic Models for K8s Specs

Container and NetworkPolicy specs are built using Pydantic models with `serialization_alias` for camelCase field names:

```python
class ContainerSpec(BaseModel):
    name: str
    image: str
    command: Optional[list[str]] = None
    env: Optional[list[EnvVar]] = None
    security_context: Optional[ContainerSecurityContext] = Field(
        default=None,
        serialization_alias="securityContext"
    )
```

Serialization via `model_dump(by_alias=True, exclude_none=True)` produces clean K8s API payloads.

## Constants

```python
# Pod-gateway image
POD_GATEWAY_IMAGE = "ghcr.io/angelnu/pod-gateway:v1.11.1"

# VXLAN defaults
DEFAULT_VXLAN_ID = 42
DEFAULT_VXLAN_IP_NETWORK = "172.16.0"
DEFAULT_VXLAN_GATEWAY_FIRST_DYNAMIC_IP = 20

# Gateway defaults
DEFAULT_VPN_INTERFACE = "tun0"
DEFAULT_VPN_BLOCK_OTHER_TRAFFIC = True

# Container names
GATEWAY_INIT_CONTAINER_NAME = "gateway-init"
GATEWAY_SIDECAR_CONTAINER_NAME = "gateway-sidecar"
CLIENT_INIT_CONTAINER_NAME = "vpn-route-init"
CLIENT_SIDECAR_CONTAINER_NAME = "vpn-route-sidecar"
```

## Relation Schema

### gluetun-k8s (metadata.yaml)

```yaml
provides:
  vpn-gateway:
    interface: vpn-gateway
```

### Download clients (metadata.yaml)

```yaml
requires:
  vpn-gateway:
    interface: vpn-gateway
    limit: 1  # Only one VPN gateway per download client
```

## Multi-Gateway Support

When deploying multiple VPN gateways (e.g., different regions):

```bash
juju deploy gluetun-k8s gluetun-us --config vxlan-id=42 --config cluster-cidrs="10.42.0.0/16 10.43.0.0/16"
juju deploy gluetun-k8s gluetun-eu --config vxlan-id=43 --config cluster-cidrs="10.42.0.0/16 10.43.0.0/16"

juju relate qbittorrent:vpn-gateway gluetun-us:vpn-gateway
juju relate sabnzbd:vpn-gateway gluetun-eu:vpn-gateway
```

Each gateway creates an isolated VXLAN overlay with its own tunnel ID. The `VXLAN_IP_NETWORK` can be the same (`172.16.0`) because different VXLAN IDs create separate overlay networks.

## Charm Usage Examples

### Provider Charm (gluetun-k8s)

```python
class GluetunCharm(CharmBase):
    def __init__(self, framework):
        super().__init__(framework)
        self.vpn_gateway = VPNGatewayProvider(self, "vpn-gateway")
        self.framework.observe(self.on.config_changed, self._reconcile)
        self.framework.observe(self.on.gluetun_pebble_ready, self._reconcile)

    def _reconcile(self, event):
        cluster_cidrs = self.config.get("cluster-cidrs", "").strip()
        if not cluster_cidrs:
            self.unit.status = BlockedStatus("cluster-cidrs config required")
            return

        provider_data = VPNGatewayProviderData(
            gateway_dns_name=f"{self.app.name}.{self.model.name}.svc.cluster.local",
            vxlan_id=self.config.get("vxlan-id", 42),
            vxlan_ip_network="172.16.0",
            cluster_cidrs=cluster_cidrs,
            vpn_connected=self._check_vpn_health(),
            external_ip=self._get_external_ip(),
        )

        # Patch our own StatefulSet with gateway containers
        patch_gateway_statefulset(
            client=Client(),
            statefulset_name=self.app.name,
            namespace=self.model.name,
            data=provider_data,
        )

        # Publish to relation
        self.vpn_gateway.publish_data(provider_data)
        self.unit.status = ActiveStatus("VPN gateway ready")
```

### Requirer Charm (qbittorrent-k8s)

```python
class QBittorrentCharm(CharmBase):
    def __init__(self, framework):
        super().__init__(framework)
        self.vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")
        self.framework.observe(self.vpn_gateway.on.changed, self._reconcile)

    def _reconcile(self, event):
        gateway = self.vpn_gateway.get_gateway()
        client = Client()

        if not gateway:
            # Relation broken or no data - cleanup
            remove_client_containers(client, self.app.name, self.model.name)
            delete_killswitch_network_policy(client, self.app.name, self.model.name)
            self.unit.status = WaitingStatus("Waiting for VPN gateway")
            return

        if not gateway.vpn_connected:
            self.unit.status = WaitingStatus("VPN gateway not connected")
            return

        # Publish our identity
        self.vpn_gateway.publish_data(VPNGatewayRequirerData(instance_name=self.app.name))

        # Patch StatefulSet with client containers
        patch_client_statefulset(client, self.app.name, self.model.name, gateway)

        # Create kill switch NetworkPolicy
        create_killswitch_network_policy(
            client,
            KillSwitchConfig(
                app_name=self.app.name,
                namespace=self.model.name,
                cluster_cidrs=gateway.cluster_cidrs.split(),
            ),
        )

        self.unit.status = ActiveStatus(f"Routing via {gateway.external_ip}")
```

## Provider-Side Patching (Gateway Containers)

The `VPNGatewayProvider` class patches the gateway charm's own StatefulSet to add pod-gateway containers. This is separate from the consumer-side patching documented above.

**Gateway containers added:**
1. **gateway_init.sh** (init container) - Creates VXLAN tunnel, sets up iptables forwarding rules, blocks non-VPN traffic
2. **gateway_sidecar.sh** (sidecar container) - Runs DHCP and DNS server for client pods

**Implementation pattern** (same strategic merge patch approach as consumer-side):

```python
class VPNGatewayProvider:
    def reconcile(self):
        """Patch gateway StatefulSet with pod-gateway containers."""

        if self._routing_method != "pod-gateway":
            return  # Future: support other routing methods

        # Build gateway init container
        gateway_init = {
            "name": "gateway-init",
            "image": "ghcr.io/angelnu/pod-gateway:v1.13.0",
            "command": ["/bin/sh", "/init/gateway_init.sh"],
            "securityContext": {"capabilities": {"add": ["NET_ADMIN"]}},
            "env": self._build_gateway_env_vars(),
        }

        # Build gateway sidecar container (DHCP + DNS servers)
        gateway_sidecar = {
            "name": "gateway-sidecar",
            "image": "ghcr.io/angelnu/pod-gateway:v1.13.0",
            "command": ["/bin/sh", "/init/gateway_sidecar.sh"],
            "ports": [
                {"name": "dhcp", "containerPort": 67, "protocol": "UDP"},
                {"name": "dns", "containerPort": 53, "protocol": "UDP"},
            ],
            "env": self._build_gateway_env_vars(),
        }

        # Patch using lightkube (same pattern as consumer patching)
        client = Client()
        sts = client.get(StatefulSet, self.app.name, namespace=self.model.name)

        # Add init container and sidecar
        if sts.spec.template.spec.initContainers is None:
            sts.spec.template.spec.initContainers = []
        sts.spec.template.spec.initContainers.append(gateway_init)

        if sts.spec.template.spec.containers is None:
            sts.spec.template.spec.containers = []
        sts.spec.template.spec.containers.append(gateway_sidecar)

        # Apply strategic merge patch
        client.patch(
            StatefulSet,
            self.app.name,
            sts,
            namespace=self.model.name,
            patch_type=PatchType.STRATEGIC
        )

    def _build_gateway_env_vars(self) -> list[dict]:
        """Build environment variables for pod-gateway gateway containers."""
        return [
            {"name": "VXLAN_ID", "value": str(self._vxlan_id)},
            {"name": "VXLAN_IP_NETWORK", "value": self._vxlan_network},
            {"name": "GATEWAY_IP", "value": self._gateway_ip},
            {"name": "CLUSTER_CIDRS", "value": self._cluster_cidrs},
            {"name": "DNS_LOCAL_CIDRS", "value": self._cluster_cidrs},
        ]
```

**Key differences from consumer patching:**
- Gateway adds **both** init container and sidecar
- Gateway containers run DHCP/DNS services (bind to ports)
- Gateway requires NET_ADMIN capability for iptables manipulation
- Gateway environment variables configure VXLAN endpoint, not client

See [networking/adr-002-vpn-gateway.md](../networking/adr-002-vpn-gateway.md) for architectural overview of why both gateway and consumer patching is necessary.
