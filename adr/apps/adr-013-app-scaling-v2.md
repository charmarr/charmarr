# Scaling Constraints and Multi-Unit Architecture

## Context and Problem Statement

Charmarr charms run applications that were designed as single-instance desktop/server applications, not distributed systems. When users scale these charms (`juju scale-application prowlarr 2`), the behavior depends on the application's architecture:

- **Arr apps** (Prowlarr, Radarr, Sonarr, Lidarr): SQLite databases with single-writer constraint
- **Download clients** (qBittorrent, SABnzbd): Independent instances with separate state
- **Infrastructure** (Storage, VPN): Stateless configuration providers

We need to define scaling behavior for each charm type and plan for future improvements.

**Key challenge:** Juju has no native `max-units` constraint. We must handle scaling defensively in charm code.

## Considered Options

### For SQLite-based Apps (Arr)
* **Option 1:** Allow scaling, hope for the best
* **Option 2:** Block scaling with error status, continue leader operation
* **Option 3:** Block scaling and stop all workloads
* **Option 4:** Use headless service FQDN to route to leader only

### For Download Clients
* **Option 1:** Block scaling (same as arr apps)
* **Option 2:** Allow scaling, each unit independent, publish list via relation
* **Option 3:** Sync credentials via peer relation, single entry point

### For Unit FQDN Discovery
* **Option 1:** Construct manually: `{app}-{unit}.{app}-endpoints.{model}.svc.cluster.local`
* **Option 2:** Use `socket.getfqdn()` which returns headless service FQDN

## Decision Outcome

### SQLite Apps (v1): Option 4 - Headless service FQDN + single unit enforcement

**The Problem:**
1. SQLite only allows single writer - concurrent writes corrupt database
2. Juju leader election is independent of pod ordinals (pod-1 can be leader while pod-0 exists)
3. K8s Service load-balances across all pods - requests hit random pod
4. Charm code runs on leader, but traffic hits any pod

**The Solution:**
1. Publish unit FQDN via `socket.getfqdn()` in relation data
2. Consumers connect directly to specific pod (bypasses Service load balancing)
3. Block scaling with `BlockedStatus` and clear remediation message
4. Single unit = headless service resolves to single pod = no load balancing

```python
def _reconcile(self, event: ops.EventBase) -> None:
    # Check for unsupported scaling
    if self.app.planned_units() > 1:
        self.unit.status = ops.BlockedStatus(
            "Scaling not supported (SQLite). Run: juju scale-application {} 1".format(
                self.app.name
            )
        )
        # Leader continues operating to maintain service
        # Non-leader units are effectively idle
        if not self.unit.is_leader():
            return

    # Normal reconciliation continues for leader...
```

**Why this works:**
- `socket.getfqdn()` returns `prowlarr-0.prowlarr-endpoints.charmarr.svc.cluster.local`
- This DNS name resolves directly to pod-0's IP
- No Service load balancing involved
- Consumers always hit the same pod
- If user mistakenly scales, traffic still works (goes to single published FQDN)

### Download Clients (v1): Block scaling, (v2): List-based multi-instance

**v1 Behavior:**
Same as arr apps - block scaling, single unit, headless service FQDN.

**v2 Enhancement:**
Download clients CAN work as independent instances. Each qBittorrent has its own torrents, own state. Radarr can use multiple download clients.

```python
# v2: Leader gathers all unit FQDNs and publishes list
class DownloadClientProviderData(BaseModel):
    # v1 fields (deprecated but kept for compatibility)
    api_url: Optional[HttpUrl] = None

    # v2 fields
    instances: list[DownloadClientInstance] = []

class DownloadClientInstance(BaseModel):
    api_url: HttpUrl  # Unit FQDN: http://qbittorrent-0.qbittorrent-endpoints...
    api_key_secret_id: Optional[str] = None
    credentials_secret_id: Optional[str] = None  # For qBittorrent (contains username + password)
    client: DownloadClient
    client_type: DownloadClientType
    instance_name: str  # "qbittorrent-0", "qbittorrent-1"
```

**How it works:**
1. Each unit stores its FQDN + credentials in peer relation data
2. Leader collects all unit data from peer relation
3. Leader publishes list of all instances via `download-client` relation
4. Consumer (Radarr) registers each as separate download client
5. Radarr distributes downloads across instances (poor man's cluster)

### Infrastructure (Storage, VPN): Scaling allowed

**Storage charm:** Provides shared PVC path via relation. Scaling doesn't affect behavior - all units publish same config. No HTTP traffic to storage charm.

**VPN charm:** Provides gateway configuration via relation. Scaling doesn't affect behavior - VXLAN config is relation-driven. Could potentially provide multiple gateways for HA (v2+).

### Unit FQDN: Option 2 - `socket.getfqdn()`

**In Juju K8s StatefulSet:**
```python
import socket

# Returns: prowlarr-0.prowlarr-endpoints.charmarr.svc.cluster.local
fqdn = socket.getfqdn()
```

Juju configures StatefulSet with:
- `spec.serviceName: <app>-endpoints` (headless service)
- Pod hostname set to `<app>-<ordinal>`
- DNS automatically resolves pod FQDN via headless service

No manual construction needed. Works automatically.

## Implementation Details

### Scaling Check (All SQLite Charms)

```python
def _check_scaling(self) -> bool:
    """Check if charm is scaled beyond supported limit.

    Returns True if scaling is OK, False if blocked.
    """
    if self.app.planned_units() > 1:
        self.unit.status = ops.BlockedStatus(
            f"Scaling not supported. Run: juju scale-application {self.app.name} 1"
        )
        return False
    return True

def _reconcile(self, event: ops.EventBase) -> None:
    if not self._check_scaling():
        if not self.unit.is_leader():
            return  # Non-leader does nothing when scaled
        # Leader continues to maintain service

    # Normal reconciliation...
```

### Headless Service FQDN for Relations

```python
def _get_unit_api_url(self) -> str:
    """Get API URL using unit's FQDN via headless service."""
    fqdn = socket.getfqdn()
    return f"http://{fqdn}:{self._port}"
```

### v2 Download Client Peer Relation

```python
# In qbittorrent charm

def _on_peer_relation_changed(self, event: ops.RelationChangedEvent) -> None:
    """Handle peer relation changes - collect all unit data."""
    if not self.unit.is_leader():
        # Non-leader publishes own data to peer relation
        self._publish_own_data_to_peer()
        return

    # Leader collects all unit data and publishes to download-client relation
    self._publish_all_instances()

def _publish_own_data_to_peer(self) -> None:
    """Publish this unit's connection info to peer relation."""
    peer = self.model.get_relation("qbittorrent-peers")
    if not peer:
        return

    peer.data[self.unit]["fqdn"] = socket.getfqdn()
    peer.data[self.unit]["port"] = str(self._port)
    peer.data[self.unit]["credentials_secret_id"] = self._credentials_secret_id

def _publish_all_instances(self) -> None:
    """Leader: Collect all unit data and publish to consumers."""
    peer = self.model.get_relation("qbittorrent-peers")
    if not peer:
        return

    instances = []
    for unit in peer.units | {self.unit}:
        unit_data = peer.data.get(unit, {})
        if "fqdn" in unit_data:
            instances.append(DownloadClientInstance(
                api_url=f"http://{unit_data['fqdn']}:{unit_data['port']}",
                credentials_secret_id=unit_data.get("credentials_secret_id"),
                client=DownloadClient.QBITTORRENT,
                client_type=DownloadClientType.TORRENT,
                instance_name=f"{self.app.name}-{unit.name.split('/')[1]}",
            ))

    provider_data = DownloadClientProviderData(instances=instances)
    self.download_client_provider.publish_data(provider_data)
```

### v2 Consumer Handling (Radarr)

```python
def _reconcile_download_clients(self) -> None:
    """Configure download clients from relation data."""
    for provider in self.download_clients.get_providers():
        # v2: Handle list of instances
        if provider.instances:
            for instance in provider.instances:
                self._add_or_update_download_client(instance)
        # v1 fallback: Single instance from legacy fields
        elif provider.api_url:
            self._add_or_update_download_client_legacy(provider)
```

## Scaling Summary by Charm Type

| Charm | v1 Behavior | v2 Enhancement | Reason |
|-------|-------------|----------------|--------|
| Prowlarr | Block, single unit | PostgreSQL → scale | SQLite single-writer |
| Radarr | Block, single unit | PostgreSQL → scale | SQLite single-writer |
| Sonarr | Block, single unit | PostgreSQL → scale | SQLite single-writer |
| Lidarr | Block, single unit | PostgreSQL → scale | SQLite single-writer |
| qBittorrent | Block, single unit | List-based multi-instance | Independent instances work |
| SABnzbd | Block, single unit | List-based multi-instance | Independent instances work |
| Plex | block, single unit | Clusterplex? | Needs investigation |
| Overseerr | TBD | TBD | Needs investigation |
| Storage | Allowed | Allowed | No HTTP, relation-only |
| VPN | Allowed | HA gateways? | No HTTP, relation-only |

## v2 PostgreSQL Migration Path (Arr Apps)

When arr apps support PostgreSQL in v2:

1. Deploy PostgreSQL charm
2. Relate arr charm to PostgreSQL
3. Charm migrates SQLite → PostgreSQL (or fresh start)
4. Remove scaling constraint
5. Switch from unit FQDN to service FQDN in relation data
6. Multiple units share PostgreSQL backend
7. Service load-balancing works correctly

```python
def _get_api_url(self) -> str:
    """Get API URL - unit FQDN for SQLite, service FQDN for PostgreSQL."""
    if self._using_postgresql():
        # Service FQDN - load balancing OK with PostgreSQL
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{self._port}"
    else:
        # Unit FQDN - direct to specific pod for SQLite
        return f"http://{socket.getfqdn()}:{self._port}"
```

## Consequences

### Good

* Clear scaling behavior documented and enforced
* `BlockedStatus` with remediation command guides users
* `socket.getfqdn()` simplifies FQDN discovery
* Headless service routing bypasses load balancing issues
* v2 path clear for both PostgreSQL (arr) and list-based (download clients)
* Infrastructure charms unaffected by scaling constraints
* Non-breaking interface evolution (add `instances` list, keep legacy fields)

### Bad

* Users cannot scale arr apps in v1 (documentation must be clear)
* v2 download client scaling requires peer relation complexity
* PostgreSQL migration in v2 requires careful planning
* No true HA for arr apps until PostgreSQL support

### Neutral

* Plex and Overseerr scaling TBD (different architecture)
* VPN HA could be v2+ enhancement but not critical

## Related MADRs

- [apps/adr-004-radarr-sonarr](./adr-004-radarr-sonarr.md) - Media manager implementation
- [apps/adr-007-qbit-sabnzbd](./adr-007-qbit-sabnzbd.md) - Download client implementation
- [apps/adr-008-prowlarr](./adr-008-prowlarr.md) - Prowlarr implementation
- [interfaces/adr-004-download-client](../interfaces/adr-004-download-client.md) - Download client interface
- [storage/adr-004-config-storage](../storage/adr-004-config-storage.md) - SQLite storage decision
