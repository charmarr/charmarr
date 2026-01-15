#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr Storage Charm - workload-less charm for shared PVC management."""

import logging
from enum import Enum

import ops
from lightkube import ApiError
from lightkube.models.core_v1 import (
    NFSVolumeSource,
    PersistentVolumeClaimSpec,
    PersistentVolumeSpec,
    VolumeResourceRequirements,
)
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import PersistentVolume, PersistentVolumeClaim

from charmarr_lib.core import (
    K8sResourceManager,
    PermissionCheckStatus,
    check_storage_permissions,
    observe_events,
    reconcilable_events_k8s_workloadless,
)
from charmarr_lib.core.interfaces import MediaStorageProvider, MediaStorageProviderData

logger = logging.getLogger(__name__)


class BackendType(str, Enum):
    """Storage backend types."""

    STORAGE_CLASS = "storage-class"
    NATIVE_NFS = "native-nfs"


class AccessMode(str, Enum):
    """PVC access modes."""

    READ_WRITE_MANY = "ReadWriteMany"
    READ_WRITE_ONCE = "ReadWriteOnce"


class CharmarrStorageCharm(ops.CharmBase):
    """Charm for managing shared media storage PVC."""

    _pvc_name = "charmarr-shared-media"
    _pv_name = "charmarr-shared-media-pv"
    _mount_path = "/data"

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._storage_provider = MediaStorageProvider(self, "media-storage")
        self._k8s: K8sResourceManager | None = None
        self._cached_pvc_backend: BackendType | None = None
        self._resize_error: str | None = None
        self._permission_error: str | None = None
        self._permission_check_pending: bool = False

        observe_events(self, reconcilable_events_k8s_workloadless, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self.on.remove, self._on_remove)

    @property
    def k8s(self) -> K8sResourceManager:
        """Lazily initialize K8s resource manager."""
        if self._k8s is None:
            self._k8s = K8sResourceManager()
        return self._k8s

    def _detect_pvc_backend(self) -> BackendType | None:
        """Detect which backend type created the existing PVC.

        Returns None if no PVC exists yet.
        """
        if self._cached_pvc_backend is not None:
            return self._cached_pvc_backend

        pvc = self._get_pvc()
        if pvc is None:
            return None

        if pvc.spec is None:
            return None

        # native-nfs: empty storageClassName and volumeName pointing to our PV
        # storage-class: non-empty storageClassName
        storage_class = pvc.spec.storageClassName
        volume_name = pvc.spec.volumeName

        if storage_class == "" and volume_name == self._pv_name:
            self._cached_pvc_backend = BackendType.NATIVE_NFS
        elif storage_class:
            self._cached_pvc_backend = BackendType.STORAGE_CLASS
        else:
            # Edge case: empty storageClassName but no volumeName - shouldn't happen
            # Treat as storage-class since that's more common
            self._cached_pvc_backend = BackendType.STORAGE_CLASS

        return self._cached_pvc_backend

    def _is_backend_change_blocked(self) -> tuple[bool, str]:
        """Check if the configured backend differs from the existing PVC's backend.

        Returns (is_blocked, message) tuple.
        """
        existing_backend = self._detect_pvc_backend()
        if existing_backend is None:
            return False, ""

        configured_backend = self.config.get("backend-type", "")
        if not configured_backend:
            return False, ""

        if configured_backend != existing_backend.value:
            return True, (
                f"Cannot change backend from '{existing_backend.value}' to '{configured_backend}'. "
                f"Redeploy with required backend (WARNING: may cause data loss)."
            )

        return False, ""

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile desired state with actual K8s state."""
        if not self.unit.is_leader():
            return

        if not self._is_config_valid():
            return

        is_blocked, _ = self._is_backend_change_blocked()
        if is_blocked:
            return

        backend_type = self.config.get("backend-type")
        if backend_type == BackendType.STORAGE_CLASS.value:
            self._reconcile_storage_class_pvc()
        elif backend_type == BackendType.NATIVE_NFS.value:
            self._reconcile_native_nfs()

        if not self._run_permission_check():
            return

        self._publish_relation_data()

    def _run_permission_check(self) -> bool:
        """Run permission check when PVC exists.

        For WaitForFirstConsumer storage classes, the permission check Job
        will be the first consumer that triggers PVC binding.

        Returns:
            True if check passed, False if pending or failed.
        """
        pvc_phase = self._get_pvc_phase()
        if pvc_phase is None:
            return False

        puid = int(self.config.get("puid", 1000))
        pgid = int(self.config.get("pgid", 1000))

        result = check_storage_permissions(
            manager=self.k8s,
            namespace=self.model.name,
            pvc_name=self._pvc_name,
            puid=puid,
            pgid=pgid,
            mount_path=self._mount_path,
        )

        if result.status == PermissionCheckStatus.FAILED:
            self._permission_error = result.message
            self._permission_check_pending = False
            self._storage_provider.clear_data()
            logger.error("Permission check failed: %s", result.message)
            return False
        elif result.status == PermissionCheckStatus.PASSED:
            self._permission_error = None
            self._permission_check_pending = False
            logger.info("Permission check passed")
            return True

        # PENDING - don't publish yet, wait for check to complete
        self._permission_check_pending = True
        logger.info("Permission check in progress")
        return False

    def _is_config_valid(self) -> bool:
        """Check if charm configuration is valid."""
        backend_type = self.config.get("backend-type", "")

        if not backend_type or backend_type not in [bt.value for bt in BackendType]:
            return False

        if backend_type == BackendType.STORAGE_CLASS.value:
            return bool(self.config.get("storage-class"))

        if backend_type == BackendType.NATIVE_NFS.value:
            return bool(self.config.get("nfs-server") and self.config.get("nfs-path"))

        return False

    def _reconcile_storage_class_pvc(self) -> None:
        """Reconcile PVC for storage-class backend."""
        pvc = self._get_pvc()

        if pvc is None:
            self._create_pvc()
            return

        self._update_pvc_size_if_needed(pvc)

    def _get_pvc(self) -> PersistentVolumeClaim | None:
        """Get the PVC if it exists."""
        try:
            return self.k8s.get(PersistentVolumeClaim, self._pvc_name, self.model.name)
        except ApiError as e:
            if e.status.code == 404:
                return None
            raise

    def _create_pvc(self) -> None:
        """Create the shared media PVC."""
        storage_class = str(self.config.get("storage-class"))
        size = str(self.config.get("size", "100Gi"))
        access_mode = str(self.config.get("access-mode", AccessMode.READ_WRITE_MANY.value))

        pvc = PersistentVolumeClaim(
            metadata=ObjectMeta(name=self._pvc_name, namespace=self.model.name),
            spec=PersistentVolumeClaimSpec(
                storageClassName=storage_class,
                accessModes=[access_mode],
                resources=VolumeResourceRequirements(requests={"storage": size}),
            ),
        )

        logger.info(
            "Creating PVC %s with storage-class %s, size %s", self._pvc_name, storage_class, size
        )
        self.k8s.apply(pvc)

    def _update_pvc_size_if_needed(self, pvc: PersistentVolumeClaim) -> None:
        """Update PVC size if config requests a larger size."""
        desired_size = str(self.config.get("size", "100Gi"))

        if pvc.spec is None or pvc.spec.resources is None:
            return

        current_requests = pvc.spec.resources.requests or {}
        current_size = current_requests.get("storage", "")

        if current_size == desired_size:
            self._resize_error = None
            return

        logger.info(
            "Updating PVC %s size from %s to %s", self._pvc_name, current_size, desired_size
        )
        patch = {"spec": {"resources": {"requests": {"storage": desired_size}}}}
        try:
            self.k8s.patch(PersistentVolumeClaim, self._pvc_name, patch, self.model.name)
            self._resize_error = None
        except ApiError as e:
            self._resize_error = f"Resize failed ({current_size} → {desired_size}): {e}"
            logger.error("Failed to resize PVC: %s", e)

    def _reconcile_native_nfs(self) -> None:
        """Reconcile PV and PVC for native-nfs backend."""
        pv = self._get_pv()
        if pv is None:
            self._create_nfs_pv()
        else:
            self._reconcile_existing_pv(pv)

        pvc = self._get_pvc()
        if pvc is None:
            self._create_nfs_pvc()
        else:
            self._log_pvc_size_mismatch(pvc)

    def _log_pvc_size_mismatch(self, pvc: PersistentVolumeClaim) -> None:
        """Log info if PVC size differs from config.

        For native-nfs, PVC size is not enforced by Kubernetes - actual capacity
        is determined by the NFS share. PVC resize is also not supported for
        statically provisioned volumes, so we just log the mismatch.
        """
        desired_size = str(self.config.get("size", "100Gi"))
        current_requests = pvc.spec.resources.requests if pvc.spec and pvc.spec.resources else {}
        current_size = (current_requests or {}).get("storage", "")

        if current_size and current_size != desired_size:
            logger.info(
                "PVC %s shows %s but config is %s. K8s does not support resizing "
                "statically provisioned PVCs, but this is cosmetic - NFS capacity "
                "is determined by the share, not the PVC",
                self._pvc_name,
                current_size,
                desired_size,
            )

    def _reconcile_existing_pv(self, pv: PersistentVolume) -> None:
        """Reconcile an existing PV with current config.

        Handles Released PVs (clears claimRef) and config drift (NFS server/path/size changes).
        """
        nfs_server = str(self.config.get("nfs-server"))
        nfs_path = str(self.config.get("nfs-path"))
        desired_size = str(self.config.get("size", "100Gi"))

        needs_update = False
        reason = ""

        if pv.status and pv.status.phase == "Released":
            logger.info("PV %s is Released, clearing claimRef for reuse", self._pv_name)
            needs_update = True
            reason = "Released state"

        if (
            pv.spec
            and pv.spec.nfs
            and (pv.spec.nfs.server != nfs_server or pv.spec.nfs.path != nfs_path)
        ):
            logger.info(
                "PV %s NFS config changed (%s:%s -> %s:%s)",
                self._pv_name,
                pv.spec.nfs.server,
                pv.spec.nfs.path,
                nfs_server,
                nfs_path,
            )
            needs_update = True
            reason = "config drift"

        current_size = pv.spec.capacity.get("storage", "") if pv.spec and pv.spec.capacity else ""
        if current_size and current_size != desired_size:
            logger.info("PV %s size changed (%s -> %s)", self._pv_name, current_size, desired_size)
            needs_update = True
            reason = "size change"

        if not needs_update:
            return

        logger.info("Updating PV %s due to %s", self._pv_name, reason)
        size = str(self.config.get("size", "100Gi"))
        updated_pv = PersistentVolume(
            metadata=ObjectMeta(name=self._pv_name),
            spec=PersistentVolumeSpec(
                capacity={"storage": size},
                accessModes=[AccessMode.READ_WRITE_MANY.value],
                persistentVolumeReclaimPolicy="Retain",
                nfs=NFSVolumeSource(server=nfs_server, path=nfs_path),
                claimRef=None,
            ),
        )
        self.k8s.apply(updated_pv, force=True)

    def _get_pv(self) -> PersistentVolume | None:
        """Get the PV if it exists."""
        try:
            return self.k8s.get(PersistentVolume, self._pv_name, namespace=None)
        except ApiError as e:
            if e.status.code == 404:
                return None
            raise

    def _create_nfs_pv(self) -> None:
        """Create the NFS-backed PersistentVolume."""
        nfs_server = str(self.config.get("nfs-server"))
        nfs_path = str(self.config.get("nfs-path"))
        size = str(self.config.get("size", "100Gi"))

        pv = PersistentVolume(
            metadata=ObjectMeta(name=self._pv_name),
            spec=PersistentVolumeSpec(
                capacity={"storage": size},
                accessModes=[AccessMode.READ_WRITE_MANY.value],
                persistentVolumeReclaimPolicy="Retain",
                nfs=NFSVolumeSource(server=nfs_server, path=nfs_path),
            ),
        )

        logger.info(
            "Creating NFS PV %s with server %s, path %s", self._pv_name, nfs_server, nfs_path
        )
        self.k8s.apply(pv)

    def _create_nfs_pvc(self) -> None:
        """Create PVC that binds to the NFS PV."""
        size = str(self.config.get("size", "100Gi"))

        pvc = PersistentVolumeClaim(
            metadata=ObjectMeta(name=self._pvc_name, namespace=self.model.name),
            spec=PersistentVolumeClaimSpec(
                storageClassName="",
                accessModes=[AccessMode.READ_WRITE_MANY.value],
                resources=VolumeResourceRequirements(requests={"storage": size}),
                volumeName=self._pv_name,
            ),
        )

        logger.info("Creating PVC %s bound to PV %s", self._pvc_name, self._pv_name)
        self.k8s.apply(pvc)

    def _get_pv_phase(self) -> str | None:
        """Get the current PV phase (Available, Bound, Released, Failed)."""
        pv = self._get_pv()
        if pv is None or pv.status is None:
            return None
        return pv.status.phase

    def _get_pvc_phase(self) -> str | None:
        """Get the current PVC phase (Pending, Bound, Lost)."""
        pvc = self._get_pvc()
        if pvc is None or pvc.status is None:
            return None
        return pvc.status.phase

    def _publish_relation_data(self) -> None:
        """Publish storage data to all related applications."""
        pvc_phase = self._get_pvc_phase()
        if pvc_phase is None:
            return

        puid = int(self.config.get("puid", 1000))
        pgid = int(self.config.get("pgid", 1000))

        data = MediaStorageProviderData(
            pvc_name=self._pvc_name,
            mount_path=self._mount_path,
            puid=puid,
            pgid=pgid,
        )
        self._storage_provider.publish_data(data)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect unit statuses from all components."""
        self._check_config_status(event)

        if not self._is_config_valid():
            return

        if not self.unit.is_leader():
            event.add_status(ops.ActiveStatus("Standby (leader manages storage)"))
            return

        self._check_pvc_status(event)

    def _check_pvc_status(self, event: ops.CollectStatusEvent) -> None:
        """Check PVC status and add relevant statuses."""
        backend_type = self.config.get("backend-type")

        if backend_type == BackendType.NATIVE_NFS.value:
            self._check_native_nfs_status(event)
            return

        if self._resize_error:
            event.add_status(ops.BlockedStatus("PVC resize failed. Check logs for details."))
            return

        if self._permission_error:
            event.add_status(ops.BlockedStatus(self._permission_error))
            return

        if self._permission_check_pending:
            event.add_status(ops.MaintenanceStatus("Checking storage permissions"))
            return

        pvc_phase = self._get_pvc_phase()

        if pvc_phase is None:
            event.add_status(ops.MaintenanceStatus("Creating PVC"))
        elif pvc_phase in ("Pending", "Bound"):
            event.add_status(ops.ActiveStatus())
        elif pvc_phase == "Lost":
            event.add_status(ops.BlockedStatus("PVC lost. Check storage backend"))

    def _check_native_nfs_status(self, event: ops.CollectStatusEvent) -> None:
        """Check native-nfs backend status (PV and PVC)."""
        pv_phase = self._get_pv_phase()
        pvc_phase = self._get_pvc_phase()

        if pv_phase is None:
            event.add_status(ops.MaintenanceStatus("Creating NFS PV"))
            return

        if pv_phase == "Failed":
            event.add_status(ops.BlockedStatus("NFS PV failed. Check NFS server"))
            return

        if pvc_phase is None:
            event.add_status(ops.MaintenanceStatus("Creating PVC"))
            return

        if self._permission_error:
            event.add_status(ops.BlockedStatus(self._permission_error))
            return

        if self._permission_check_pending:
            event.add_status(ops.MaintenanceStatus("Checking storage permissions"))
            return

        if pvc_phase in ("Pending", "Bound"):
            event.add_status(ops.ActiveStatus())
        elif pvc_phase == "Lost":
            event.add_status(ops.BlockedStatus("PVC lost. Check NFS server"))

    def _check_config_status(self, event: ops.CollectStatusEvent) -> None:
        """Check configuration and add relevant statuses."""
        backend_type = self.config.get("backend-type", "")

        if not backend_type:
            event.add_status(ops.BlockedStatus("backend-type not configured"))
            return

        if backend_type not in [bt.value for bt in BackendType]:
            event.add_status(
                ops.BlockedStatus(
                    f"Invalid backend-type: {backend_type}. Use 'storage-class' or 'native-nfs'"
                )
            )
            return

        is_blocked, message = self._is_backend_change_blocked()
        if is_blocked:
            event.add_status(ops.BlockedStatus(message))
            return

        if backend_type == BackendType.STORAGE_CLASS.value:
            if not self.config.get("storage-class"):
                event.add_status(ops.BlockedStatus("storage-class not configured"))

        elif backend_type == BackendType.NATIVE_NFS.value:
            if not self.config.get("nfs-server"):
                event.add_status(ops.BlockedStatus("nfs-server not configured"))
            if not self.config.get("nfs-path"):
                event.add_status(ops.BlockedStatus("nfs-path not configured"))

    def _on_remove(self, event: ops.RemoveEvent) -> None:
        """Clean up storage resources on charm removal."""
        if not self.unit.is_leader():
            return

        if not self.config.get("cleanup-on-remove", False):
            logger.info("Skipping cleanup (cleanup-on-remove=false)")
            return

        # Only cleanup when application is fully removed, not during scale-down
        if self.model.app.planned_units() > 0:
            logger.info("Skipping cleanup (application not being removed)")
            return

        backend_type = self.config.get("backend-type")
        if backend_type == BackendType.NATIVE_NFS.value:
            self.k8s.delete(PersistentVolume, self._pv_name, namespace=None)
            logger.info("Deleted PV %s", self._pv_name)

        self.k8s.delete(PersistentVolumeClaim, self._pvc_name, self.model.name)
        logger.info("Deleted PVC %s", self._pvc_name)


if __name__ == "__main__":
    ops.main(CharmarrStorageCharm)
