# Storage Charm as PVC Lifecycle Manager

**Status:** Accepted

**Related ADRs:**
- [ADR-001: Shared PVC Architecture](adr-001-shared-pvc-architecture.md) - Establishes the need for a shared PVC
- [ADR-003: PVC Patching in Arr Charms](adr-003-pvc-patching-in-arr-charms.md) - Defines how consuming charms receive and use PVC information

## Context and Problem Statement

With the decision to use a shared PVC for all arr applications (see [ADR-001](adr-001-shared-pvc-architecture.md)), we need to determine who is responsible for creating and managing this PVC's lifecycle, including initial provisioning, expansion, and configuration. The PVC needs to be created before any arr charms can mount it, and expansion operations need to be coordinated. Should this PVC be managed by infrastructure tooling (Terraform), by each consuming charm independently, or by a dedicated storage management charm?

## Considered Options

* Create PVC directly in Terraform and pass the name to charms via configuration
* Have each arr charm attempt to create/claim the shared PVC independently
* Create a dedicated charmarr-storage charm that owns and manages the PVC lifecycle
* Use Juju storage pools and let Juju handle PVC creation per standard patterns

## Decision Outcome

Chosen option: "Create a dedicated charmarr-storage charm that owns and manages the PVC lifecycle", because this keeps all operational concerns of charmarr the Juju model rather than split between Terraform and Juju. A storage charm can expose the PVC details through Juju relations, handle expansion through standard charm configuration, implement proper reconciliation patterns, and maintain observable state through Juju status. This provides a clean separation where the storage charm owns storage concerns and arr charms own application concerns. Its important to note that the storage charm won't be responsible for special (for eg. HA storages) storage classes and CSIs. It will only handle K8s native NFS driver if the user wishes to use that, if not it's the user's responsibility to setup the K8s storage class and instruct the storage charm to use that.

### Implementation Details

**Charm Configuration:**

The storage charm exposes the following configuration options:
- `backend-type`: Required, one of "storage-class", "native-nfs", or "hostpath", determines which resources the charm manages
- `storage-class`: Which Kubernetes StorageClass to use (e.g., "topolvm-provisioner", "local-path", "nfs-csi")
- `nfs-server`: For charmarr managed K8s native NFS driver, the NFS server IP address or hostname
- `nfs-path`: For charmarr managed K8s native NFS driver, the export path on the NFS server
- `hostpath`: Host filesystem path for single-node deployments (e.g., "/media", "/mnt/storage/charmarr")
- `size`: Storage capacity to provision (see [ADR-001](adr-001-shared-pvc-architecture.md) for access mode and provisioning details)

**Backend Selection Guidance:**

The choice of storage backend depends on your deployment scenario:

**Use hostpath backend when:**
- Running single-node clusters (MicroK8s, k3s, kind)
- You have existing local storage with filesystem-level redundancy (ZFS, BTRFS)
- You want direct host filesystem access without StorageClass complexity
- Best for homelab/testing scenarios with pre-existing storage

**Use storage-class backend when:**
- You have a Kubernetes StorageClass already configured
- You want the CSI driver to handle provisioning and expansion
- Examples: local-path, topolvm-provisioner, nfs-csi

**Use native-nfs backend when:**
- **Going multi-node** - NFS provides ReadWriteMany access so pods can be scheduled on any node
- You have a dedicated NAS appliance (Synology, TrueNAS, etc.) that handles redundancy
- Your media storage is already on a network file server
- You want storage to survive complete cluster rebuilds
- Network latency is acceptable for your workload (media files are large, not latency-sensitive)

For HA, other than NFS, also consider other solutions including Rook-Ceph and GlusterFS.

Again, charmarr will never handle setting up or configuring different storage backends. User is responsible for setting up the StorageClass and passing it down to the storage charm. Only exceptions being the K8s native NFS driver and hostpath (because they're K8s native and simple).

**Reconciler Pattern:**

The charm implements a reconciler that continuously ensures actual state matches desired state. The reconciler is triggered by:
- Config-changed events when the user modifies charm configuration
- Update-status events for periodic health checks
- Relation events when consuming charms connect or disconnect

The reconciler workflow:
1. Check if required Kubernetes resources exist (PVC for `storage-class`, PV and PVC for `native-nfs` and `hostpath`)
2. Compare current resource specifications with desired configuration
3. Create missing resources or patch existing ones to match desired state
4. Watch for resource conditions indicating success or failure
5. Update charm status and relation data accordingly

**Reactive Error Handling:**

The charm uses a reactive rather than proactive validation approach. Instead of attempting to verify that the underlying storage backend has sufficient capacity before requesting resources, the charm requests what the user configured and handles failures when they occur.

For storage classes, the CSI driver will/might fail the expansion and report this through PVC conditions. The charm reconciler detects this failure condition and transitions to error status with the message from the CSI driver.

For K8s native NFS, the Kubernetes-level updates succeed since they're just metadata, but applications may encounter disk full errors when attempting to use the space. The charm relies on observability integration with the COS stack to monitor actual filesystem usage and alert when capacity is reached.

This reactive approach is chosen because proactive validation would require the charm to inspect infrastructure details (LVM volume groups, NFS server capacity) that are outside its proper scope and would require additional permissions and complexity. Users are expected to ensure their infrastructure has sufficient capacity before requesting expansions.

**Charm Status State Machine:**

- **Maintenance**: During initial setup or expansion operations while resources are being created/updated
- **Active**: Resources are created, bound, and ready for use; relation data is current
- **Error**: Resource creation or expansion failed (e.g., insufficient storage capacity, invalid configuration)
- **Blocked**: Cannot proceed due to missing required configuration (e.g., backend-type not set)

**Relation Interface:**

The charm provides a relation endpoint called `shared-storage` that exposes:
```python
{
    "pvc-name": "charmarr-shared-media",
    "size": "2Ti",
    "mount-path": "/data",
    "backend-type": "storage-class"  # or "native-nfs"
}
```

When the storage size is expanded, the charm updates this relation data, triggering relation-changed events in all connected consuming charms. Consuming charms don't need to take action on size changes since their existing volume mounts automatically reflect the expanded capacity, but they can use this information to update status displays or trigger other logic.

### Consequences

* Good, because storage lifecycle is managed through standard Juju patterns (deploy, configure, relate)
* Good, because expansion is triggered through charm configuration rather than manual Terraform reapply or kubectl commands
* Good, because storage state is visible through Juju status and relations rather than requiring kubectl inspection
* Good, because the storage charm can implement reconciliation logic to handle failures and ensure desired state
* Good, because relation data provides a clean interface for arr charms to discover PVC name and configuration
* Good, because reactive error handling keeps the charm implementation simple and focused
* Good, because charm status clearly communicates the state of storage operations to users
* Bad, because adds one more charm to deploy compared to having Terraform create the PVC directly
* Bad, because storage charm needs backend-specific logic for different storage types (storage-class vs nfs)
* Bad, because reactive error handling means users may not discover capacity issues until after requesting expansion
* Bad, because the charm requires RBAC permissions to create and modify cluster-level resources like PersistentVolumes
