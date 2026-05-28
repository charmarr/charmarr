# Backup and Recovery Strategy for Charmarr Services

## Context and Problem Statement

Charmarr services store critical configuration and application state that must survive disasters. We need a backup and recovery strategy that:
- Protects against data loss for all services
- Supports disaster recovery scenarios with acceptable RPO/RTO
- Integrates cleanly with Kubernetes and Juju
- Handles PVC backups for config storage [ADR 004](adr-004-config-storage.md)
- Minimizes operational complexity and infrastructure overhead
- Works within realistic resource constraints for homelab deployments

A critical challenge emerged: the restore process must work with Juju's storage model, where StatefulSets automatically create PVCs on deployment, potentially conflicting with PVCs restored from backup.

## Considered Options

* **Option 1**: Charmed Velero with S3-compatible storage
* **Option 2**: PostgreSQL S3 backups for arr apps + Velero for others (hybrid)
* **Option 3**: Raw Velero deployment with external S3 (no Juju integration)

## Decision Outcome

Chosen option: **"Option 1: Charmed Velero with S3 like backend"**, because it provides a unified backup solution, requires minimal infrastructure (a S3 like storage), integrates cleanly with Juju through the `velero-backup-config` relation, and has stable support in Juju 3.6+ for the critical import-filesystem workflow. Important to make sure the configuration only backs up the config PVC (there could be others like logs which might make backups very expensive).

### Consequences

* Good, because single unified backup system for all Charmarr services (no special cases)
* Good, because uses Canonical's officially supported pattern with documentation and community validation
* Good, because automated backups via relation (charms declare backup spec, Velero handles scheduling)
* Good, because Juju 3.6+ has stable `import-filesystem` support (no experimental features or flags required)
* Good, because something like MinIO can run in-cluster (no external dependencies) or use external S3
* Good, because Velero automatically labels restored resources (`velero.io/restore-name`, `velero.io/backup-name`) making them easily identifiable among hundreds of PVs
* Good, because proven at scale (Velero is industry standard for K8s backup)
* Good, because relation-based integration means charms just provide spec - no manual CRD creation
* Bad, because restore process is semi-manual (requires kubectl + juju commands, though acceptable for disaster recovery)
* Bad, because all services share same backup schedule initially (cannot configure different frequencies per service)
* Bad, because requires MinIO deployment (adds one service to manage, though minimal overhead)
* Bad, because restore is slower than PostgreSQL-based alternatives (2-5 min per service vs 30 sec)
* Bad, because documentation burden - users need clear step-by-step restore instructions

## Detailed Analysis of Rejected Options

### Why Not Option 2: PostgreSQL Backups + Velero Hybrid?

**The hybrid approach**: Use PostgreSQL with S3 backups for arr apps (Radarr/Sonarr/Prowlarr), use Velero for everything else (qBittorrent, SABnzbd, Jellyfin, Plex).

**Initial appeal**:
- Faster restore for arr apps (30 sec vs 2-5 min) - PostgreSQL restores and apps auto-reconnect
- Unified backup for arr configs via PostgreSQL's built-in S3 integration
- Leverage PostgreSQL's native backup capabilities (pgBackRest in charmed-postgres-k8s)

**Why we rejected it**:

Major reason for not choosing this is we can't force Postgresql on users when the upstream doesn't demand it mandatorily. And the charms won't support PostgresQL in v1 anyway. Especially with the infrastructure overhead that comes in with hosting another service (PostgresQL). So the base safety that Charmarr will provide is Velero based backups for all the charms in v1. But in Charmarr v2 when charms support PostgresQL, velero backups for those charms can be disabled.

### Why Not Option 3: Raw Velero Without Juju Integration?

**The approach**: Deploy Velero manually via helm/kubectl, manage backups via velero CLI, skip Juju integration.

**Why we rejected it**:

1. **Canonical provides Charmed Velero**: There's an official charm that handles all the complexity. Why reinvent it?

2. **Lose automation benefits**:

3. **No Juju integration**:

4. **Restore workflow is messier**:

5. **Charmed Velero provides**:
   - Relation-based backup configuration
   - Juju actions for common operations (list-backups, restore)
   - Integration with s3-integrator
   - Consistent with Charmarr's "Juju-native" approach

**Verdict**: Using Charmed Velero is the obvious choice given it exists and is supported.

## Critical Technical Challenges Solved

### Challenge 1: Velero vs Juju Storage Model Conflict

**Problem discovered**: When you `juju deploy radarr`, Juju creates a StatefulSet with volumeClaimTemplates. This automatically creates new PVCs (e.g., `radarr-config-radarr-0`). When Velero restores PVCs from backup, they have the same names. How do you get Juju to use the restored PVCs instead of creating new ones?

**Initial assumption (wrong)**: Deploy charm, then run restore action, charm handles it.

**Reality**: StatefulSet creates PVCs immediately on deploy. By the time charm code runs, new empty PVCs already exist.

**Solution**: Restore PVCs **before** deploying the charm:
1. Trigger Velero restore (creates PVCs from backup)
2. Import PVCs into Juju's storage model (`juju import-filesystem`)
3. Deploy charm with `--attach-storage` flag pointing to imported storage

**Key Juju 3.6 feature**: `import-filesystem` for Kubernetes is stable (no experimental flags). It allows:
- Importing existing unbound PVs into Juju's storage tracking
- Using `--force` flag to handle PVs that still have PVC references
- Attaching imported storage at deploy time with `--attach-storage`

This is confirmed.

### Challenge 2: Finding Restored PVs Among Hundreds

**Problem**: After Velero restore, `kubectl get pv` might show 100+ PVs. How do you find the specific ones for radarr?

**Solution**: Velero automatically labels all restored resources:
- `velero.io/restore-name=<restore-name>`
- `velero.io/backup-name=<backup-name>`

Finding restored PVs:
```bash
kubectl get pv -l velero.io/restore-name=radarr-backup-20251129 \
  -l app.kubernetes.io/name=radarr
```

This filters to exactly the PVs you need. Not guessing, not searching through lists.

### Challenge 3: Local Storage vs S3 Requirement

**Discovery**: Both Velero and PostgreSQL require S3-compatible storage:
- Velero officially requires object storage (S3 API)
- PostgreSQL charmed operator requires S3 via s3-integrator
- Neither supports true local filesystem backups out of the box

**Community workaround exists**: There's an unofficial Velero plugin for local storage, but:
- Not officially supported by Velero project
- Has limitations (documented issues with multi-node clusters)
- Adds maintenance burden

**Possible Self-hosted Solution**: Use Charmed-MinIO as S3-compatible object storage:
- Can run in-cluster (no external dependencies)
- Provides S3 API that both Velero and PostgreSQL can use
- Minimal resource overhead (can run on small storage PVC)
- Can later migrate to external S3 (AWS, Backblaze B2, etc.) without changing backup architecture

## Implementation Details

### Infrastructure (deployed via Terraform)

```hcl
resource "juju_application" "velero_operator" {
  name  = "velero-operator"
  model = juju_model.charmarr.name

  charm {
    name    = "velero-operator"
    channel = "stable"
  }

  trust = true
}

resource "juju_application" "s3_integrator" {
  name  = "s3-integrator"
  model = juju_model.charmarr.name

  charm {
    name    = "s3-integrator"
    channel = "stable"
  }

  config = {
    endpoint = var.minio_endpoint
    bucket   = "charmarr-backups"
  }
}

resource "juju_application" "minio" {
  name  = "minio-operator"
  model = juju_model.charmarr.name

  charm {
    name    = "minio-operator"
    channel = "stable"
  }
}

resource "juju_integration" "velero_s3" {
  model = juju_model.charmarr.name

  application {
    name = juju_application.velero_operator.name
    endpoint = "s3-credentials"
  }

  application {
    name = juju_application.s3_integrator.name
  }
}
```

### Charm Integration (using official library)

Reference implementation from canonical/minio-operator:

```python
from charms.velero_libs.v0.velero_backup_config import VeleroBackupProvider

class RadarrCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        # Provide backup configuration to Velero
        self.backup = VeleroBackupProvider(
            self,
            relation_name="velero-backup-config",
            backup_spec={
                # Only backup this namespace
                "includedNamespaces": [self.model.name],

                # Only backup resources with this label
                "labelSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": self.app.name
                    }
                },

                # Retention: 30 days
                "ttl": "720h0m0s",
            }
        )
```

The library handles:
- Relation data exchange with Velero charm
- Backup spec validation
- Automatic backup scheduling (Velero charm creates Schedule CRD)

Charmarr charms just declare what to backup. Velero does the rest.

### Backup Operation (Automatic)

Once relation is established:
1. Velero charm reads backup spec from relation
2. Creates Velero Schedule CRD for daily backups
3. Backups run automatically at configured time
4. PVCs are backed up via volume snapshots (if supported) or file system backup
5. Backup data stored in a S3 bucket

Users can check backup status:
```bash
juju run velero-operator/0 list-backups
```

### Restore Workflow (Semi-Manual)

**Complete disaster scenario** (application was deleted):

```bash
# Step 1: List available backups
juju run velero-operator/0 list-backups

# Output shows backup metadata including:
# - backup-id: radarr-backup-20251129-abc123
# - created: 2025-11-29T02:00:00Z
# - status: Completed

# Step 2: Trigger Velero restore
juju run velero-operator/0 restore backup-uid=radarr-backup-20251129-abc123

# This creates Velero Restore CRD
# Velero restores PVCs from snapshot/backup

# Step 3: Find the restored PV using Velero's labels
RESTORE_NAME="radarr-backup-20251129-abc123"
PV_NAME=$(kubectl get pv \
  -l velero.io/restore-name=$RESTORE_NAME \
  -l app.kubernetes.io/name=radarr \
  -o jsonpath='{.items[0].metadata.name}')

echo "Restored PV: $PV_NAME"

# Step 4: Import PV into Juju's storage model
juju import-filesystem kubernetes $PV_NAME radarr-config --force

# The --force flag:
# - Changes PV reclaim policy to Retain if needed
# - Deletes bound PVC if it exists
# - Clears claimRef to make PV available

# Step 5: Get the storage ID Juju assigned
STORAGE_ID=$(juju storage --format=json | \
  jq -r '.storage[] | select(.storage == "radarr-config") | ."storage-id"')

echo "Juju storage ID: $STORAGE_ID"

# Step 6: Deploy charm with restored storage attached
juju deploy radarr --attach-storage $STORAGE_ID

# Juju:
# - Creates StatefulSet
# - Sees storage already exists
# - Binds to existing PVC instead of creating new one
# - Pod starts with restored data

# Step 7: Verify service is running
juju status radarr
```

**For multiple services**, repeat steps 3-6 for each application.

**Pod failure scenario** (simpler - PVC still exists):
- Kubernetes automatically recreates pod
- StatefulSet binds to same PVC
- No restore needed - data persists
- Recovery time: 30-60 seconds

## Why Semi-Manual Restore is Acceptable

**Why not fully automate?**

1. **Restore is a rare operation**: Disaster recovery happens maybe once a year for typical homelab. Spending weeks building automation for a yearly task isn't efficient.

2. **Manual process is safer**: Restores are high-stakes operations. Human verification at each step prevents mistakes like restoring the wrong backup.

3. **Automation is complex**:
   - Running `juju` commands from inside a charm pod requires CLI access (not trivial)
   - Cross-charm coordination (which services to restore, in what order)
   - Error handling (what if restore partially fails?)
   - State management (tracking restore progress across multiple services)

4. **Documented steps work**: With clear documentation, even novice users can follow the workflow. The commands are copy-paste with one variable substitution (backup-uid).

5. **Future enhancement path**: Configuratarr TUI can automate this later without changing the underlying architecture. The TUI has full CLI access and can orchestrate the workflow interactively.

**What we provide**:
- Clear step-by-step documentation
- Helper scripts to automate the kubectl filtering
- Juju actions for common operations (list-backups)
- Error messages with next steps

## Storage Requirements (+ MinIO)

**MinIO deployment sizing if using MinIO**:
- Backup size ≈ sum of all config PVCs (typically 1-5GB each)
- With 7 services × 3GB average = 21GB active data
- With 30 days retention + compression ≈ 50-100GB total
- Recommend 100GB PVC for MinIO for safety margin

**MinIO can be switched**:
- Configure s3-integrator with external S3 credentials
- Supports AWS S3, Backblaze B2, Wasabi, any S3-compatible service
- No changes to Velero or charm code needed

## Future Enhancements

**v2 considerations**:

1. **Configuratarr DR Wizard**: Interactive TUI that:
   - Lists backups visually
   - Guides through restore with progress bars
   - Handles all kubectl/juju commands automatically
   - Validates each step before proceeding

2. **Per-service backup schedules**: If users request different backup frequencies:
   - Extend backup spec to include schedule field
   - Velero charm creates separate Schedules per service

3. **External S3 as default**:
   - Document external S3 setup as primary path
   - Keep MinIO as fallback for airgapped/local scenarios

4. **Backup health monitoring**: Integrate with COS stack:
   - Alert if backups fail
   - Dashboard showing backup age, size, success rate
   - Automated test restores to verify backup integrity

5. **Automated restore action**: If Juju CLI access from charm is solved:
   - Add `juju run radarr/leader restore-from-backup backup-id=...`
   - Charm orchestrates the import-filesystem + redeploy
   - Requires running juju commands from charm pod (currently complex)

**v1 scope**: Stick with documented manual restore. Proven to work, keeps implementation simple.
