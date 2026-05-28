# Config Storage Architecture for Charmarr Services

## Context and Problem Statement

Charmarr charms need persistent storage for application configuration and state data. Different applications have varying database support:
- **Arr apps** (Radarr v4+, Sonarr v4+, Prowlarr): Support both SQLite and PostgreSQL
- **Download clients** (qBittorrent, SABnzbd): SQLite + ini files only
- **Media servers** (Jellyfin, Plex): SQLite only

We need to decide on a storage architecture that:
- Ensures data persistence across pod restarts and failures
- Supports backup and disaster recovery
- Balances operational complexity with reliability
- Works within Juju's storage model and Kubernetes constraints
- Enables the leader-only HA pattern required by these applications (they don't support true multi-instance operation)

The decision significantly impacts infrastructure complexity, backup strategy, restore speed, and operational overhead.

## Considered Options

* **Option 1**: Native databases (SQLite/ini files) on Juju-managed PVC storage
* **Option 2**: PostgreSQL for arr apps + native databases for others (hybrid approach)
* **Option 3**: PostgreSQL for all services with charm-level state synchronization

## Decision Outcome

Chosen option: **"Option 1: Native databases on Juju-managed storage"**, because it provides the simplest architecture with minimal operational overhead while meeting all functional requirements. Charmarr v1 wouldn't support HA, but PostgreSQL support will be added to charms whose upstream supports it for v2.

### Consequences

* Good, because each service uses its battle-tested native storage format with no migration risk
* Good, because Juju's storage abstraction handles PVC lifecycle automatically via StatefulSet volumeClaimTemplates
* Good, because zero additional infrastructure to deploy (no PostgreSQL cluster, no s3-integrator for PostgreSQL)
* Good, because simpler charm code with no database schema management, migrations, or connection pooling
* Good, because fewer services to monitor and maintain (2 backup services vs 4 with PostgreSQL option)
* Good, because unified backup approach via Velero for all services (backup strategy to be documented)
* Bad, because restore operations take longer (2-5 min per service vs 30 sec with PostgreSQL)
* Bad, because SQLite databases cannot be shared across instances (but applications don't support this anyway)
* Bad, because no automatic recovery on restore (requires manual juju commands, though could be automated in Configuratarr later)

## Detailed Analysis of Rejected Options

### Why Not Option 2: PostgreSQL for Arr Apps?

**Initial appeal**: Arr apps support PostgreSQL, which seemed like it could provide faster restores and unified backups.

**PostgreSQL benefits that seemed attractive**:
- Faster restore time (30 seconds vs 2-5 minutes) - PostgreSQL data survives pod restarts
- Auto-recovery: When PostgreSQL is restored, arr apps automatically reconnect with all data intact
- Better fit for Kubernetes: PostgreSQL handles concurrent connections better than SQLite
- Unified backup: All arr configs in one PostgreSQL cluster backup
- No config PVCs needed for arr apps (data lives in PostgreSQL)

**Why we rejected it**:

1. **Still need resilient storage for other charms**: qBittorrent, SABnzbd, Jellyfin, and Plex don't support PostgreSQL. So for v1, it's decided that a standard storage concept will be implemented across all the charms.

2. **Minimal restore time benefit for use case**: For a media server, disaster recovery happens maybe once a year. Saving 2 minutes per service (6 minutes total for 3 arr apps) doesn't justify doubling the infrastructure for v1.

3. **Operational overhead**: PostgreSQL cluster needs:
   - Connection limits management
   - Query performance monitoring
   - Database size monitoring
   - Backup verification
   - Failover testing
   - Version upgrade planning

**When PostgreSQL might make sense**: For Charmarr v2 with HA support.

### Why Not Option 3: PostgreSQL for All with Charm Sync?

**The crazy idea**: Store charm state (configs, API keys, metadata) in PostgreSQL for ALL services, even those that don't natively support it. The charm would:
- Write application config to PostgreSQL on changes
- Reconstitute local SQLite/ini files from PostgreSQL on restore
- Provide unified backup via PostgreSQL S3 backups

**Why we rejected it**:

1. **PostgreSQL restore doesn't trigger Juju events**: When you restore a PostgreSQL backup, the data comes back but the database relation doesn't emit new events. Charms wouldn't know a restore happened unless they poll constantly.

2. **Complex state synchronization**: Charms would need to:
   - Serialize SQLite databases to PostgreSQL (not trivial)
   - Detect when restored data is newer than local files
   - Handle conflicts between local and PostgreSQL state
   - Implement polling or version/epoch tracking

3. **Data duplication**: Application data exists in TWO places:
   - Local SQLite/ini files (workload reads this)
   - PostgreSQL (backup copy)
   - Risk of divergence, doubled storage

4. **No clear trigger for restore**: Without events, charms would need either:
   - Constant polling (wasteful)
   - Manual restore action anyway (defeats the purpose)
   - Epoch/version tracking (adds complexity)

5. **Charm complexity explosion**: Every charm needs PostgreSQL serialization logic, restore detection, conflict resolution - this is significant engineering work for marginal benefit.

**Verdict**: This approach trades simple infrastructure for complex charm logic without solving the fundamental restore triggering problem.

## Implementation Details

### Juju Storage Declaration

Each charm declares storage in `metadata.yaml`:
```yaml
storage:
  config:
    type: filesystem
    location: /config
    minimum-size: 1G
```

### How Juju Storage Works

Juju automatically:
- Creates PVCs via StatefulSet volumeClaimTemplates with deterministic names
- Mounts storage at `/config` in the container
- Handles storage lifecycle (creation, attachment, deletion)
- Preserves PVCs even when pods restart (StatefulSet guarantee)

Users can optionally specify storage size and pool at deploy time:
```bash
# Use default storage class
juju deploy radarr

# Specify size
juju deploy radarr --storage config=5G

# Specify size and storage pool/class
juju deploy radarr --storage config=5G,fast-ssd
```

Juju queries available Kubernetes StorageClasses and exposes them as storage pools. The cluster's default StorageClass is used if none specified.

### Storage vs Media Storage

**Important distinction**: This decision covers **config storage only**. Media storage (the shared `/data` directory for hardlinks) still requires the storage charm approach [ADR 001](adr-001-shared-pvc-architecture.md) because:
- Juju storage is scoped per-application
- Media must be shared across applications (radarr, sonarr, qbittorrent all need the same `/data`)
- Juju's storage model doesn't support cross-application shared PVCs
- Storage charm creates one shared PVC outside Juju's model and provides it via relation

This is the right separation of concerns:
- **Juju storage**: Per-application config (isolated)
- **Storage charm**: Cross-application media (shared)

## Future Considerations

**For v2 or later**, we could revisit PostgreSQL as an **optional** feature:
- Add PostgreSQL support as a charm config option
- Let advanced users choose PostgreSQL if they want faster restores
- Maybe all the upstream services support PostgreSQL by then (?)
