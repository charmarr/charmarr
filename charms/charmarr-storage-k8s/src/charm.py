#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr Storage Charm - workload-less charm for shared PVC management."""

import logging
from enum import Enum

import ops
from lightkube import ApiError
from lightkube.models.core_v1 import PersistentVolumeClaimSpec, VolumeResourceRequirements
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import PersistentVolume, PersistentVolumeClaim

from _storage import (
    create_hostpath_pv,
    create_nfs_pv,
    create_static_pvc,
    get_pv,
    get_pvc,
    log_static_pv_size_mismatch,
    reconcile_existing_hostpath_pv,
    reconcile_existing_nfs_pv,
)
from charmarr_lib.core import (
    K8sResourceManager,
    PermissionCheckStatus,
    check_storage_permissions,
    delete_permission_check_job,
    observe_events,
    reconcilable_events_k8s_workloadless,
)
from charmarr_lib.core.interfaces import MediaStorageProvider, MediaStorageProviderData

logger = logging.getLogger(__name__)


class BackendType(str, Enum):
    """Storage backend types."""

    STORAGE_CLASS = "storage-class"
    NATIVE_NFS = "native-nfs"
    HOSTPATH = "hostpath"


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

        pvc = get_pvc(self.k8s, self._pvc_name, self.model.name)
        if pvc is None:
            return None

        if pvc.spec is None:
            return None

        if pvc.spec.storageClassName:
            self._cached_pvc_backend = BackendType.STORAGE_CLASS
            return self._cached_pvc_backend

        self._cached_pvc_backend = self._detect_static_pv_backend()
        return self._cached_pvc_backend

    def _detect_static_pv_backend(self) -> BackendType:
        """Detect backend type from static PV (native-nfs or hostpath)."""
        pv = get_pv(self.k8s, self._pv_name)
        if pv and pv.spec:
            if pv.spec.hostPath:
                return BackendType.HOSTPATH
            if pv.spec.nfs:
                return BackendType.NATIVE_NFS
        return BackendType.NATIVE_NFS

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
        elif backend_type == BackendType.HOSTPATH.value:
            self._reconcile_hostpath()

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

        try:
            result = check_storage_permissions(
                manager=self.k8s,
                namespace=self.model.name,
                pvc_name=self._pvc_name,
                puid=puid,
                pgid=pgid,
                mount_path=self._mount_path,
            )
        except Exception:
            self._permission_error = "Permission check failed. Bad storage backend"
            self._permission_check_pending = False
            self._storage_provider.clear_data()
            logger.error("Permission check error: %s", self._permission_error)
            return False

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

        if backend_type == BackendType.HOSTPATH.value:
            return bool(self.config.get("hostpath"))

        return False

    def _reconcile_storage_class_pvc(self) -> None:
        """Reconcile PVC for storage-class backend."""
        pvc = get_pvc(self.k8s, self._pvc_name, self.model.name)

        if pvc is None:
            self._create_storage_class_pvc()
            return

        self._update_pvc_size_if_needed(pvc)

    def _create_storage_class_pvc(self) -> None:
        """Create the shared media PVC using a StorageClass."""
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
        nfs_server = str(self.config.get("nfs-server"))
        nfs_path = str(self.config.get("nfs-path"))
        size = str(self.config.get("size", "100Gi"))
        access_mode = AccessMode.READ_WRITE_MANY.value

        pv = get_pv(self.k8s, self._pv_name)
        if pv is None:
            create_nfs_pv(self.k8s, self._pv_name, nfs_server, nfs_path, size, access_mode)
        else:
            reconcile_existing_nfs_pv(
                self.k8s, pv, self._pv_name, nfs_server, nfs_path, size, access_mode
            )

        pvc = get_pvc(self.k8s, self._pvc_name, self.model.name)
        if pvc is None:
            create_static_pvc(
                self.k8s, self._pvc_name, self._pv_name, self.model.name, size, access_mode
            )
        else:
            log_static_pv_size_mismatch(pvc, self._pvc_name, size)

    def _reconcile_hostpath(self) -> None:
        """Reconcile PV and PVC for hostpath backend."""
        hostpath = str(self.config.get("hostpath"))
        size = str(self.config.get("size", "100Gi"))
        access_mode = AccessMode.READ_WRITE_MANY.value

        pv = get_pv(self.k8s, self._pv_name)
        if pv is None:
            create_hostpath_pv(self.k8s, self._pv_name, hostpath, size, access_mode)
        else:
            reconcile_existing_hostpath_pv(
                self.k8s, pv, self._pv_name, hostpath, size, access_mode
            )

        pvc = get_pvc(self.k8s, self._pvc_name, self.model.name)
        if pvc is None:
            create_static_pvc(
                self.k8s, self._pvc_name, self._pv_name, self.model.name, size, access_mode
            )
        else:
            log_static_pv_size_mismatch(pvc, self._pvc_name, size)

    def _get_pv_phase(self) -> str | None:
        """Get the current PV phase (Available, Bound, Released, Failed)."""
        pv = get_pv(self.k8s, self._pv_name)
        if pv is None or pv.status is None:
            return None
        return pv.status.phase

    def _get_pvc_phase(self) -> str | None:
        """Get the current PVC phase (Pending, Bound, Lost)."""
        pvc = get_pvc(self.k8s, self._pvc_name, self.model.name)
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
            self._check_static_pv_status(event, "NFS")
            return

        if backend_type == BackendType.HOSTPATH.value:
            self._check_static_pv_status(event, "hostPath")
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

    def _check_static_pv_status(self, event: ops.CollectStatusEvent, pv_type: str) -> None:
        """Check static PV backend status (native-nfs or hostpath)."""
        pv_phase = self._get_pv_phase()
        pvc_phase = self._get_pvc_phase()

        if pv_phase is None:
            event.add_status(ops.MaintenanceStatus(f"Creating {pv_type} PV"))
            return

        if pv_phase == "Failed":
            event.add_status(ops.BlockedStatus(f"{pv_type} PV failed. Check storage backend"))
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
            event.add_status(ops.BlockedStatus(f"PVC lost. Check {pv_type} backend"))

    def _check_config_status(self, event: ops.CollectStatusEvent) -> None:
        """Check configuration and add relevant statuses."""
        backend_type = self.config.get("backend-type", "")

        if not backend_type:
            event.add_status(ops.BlockedStatus("backend-type not configured"))
            return

        if backend_type not in [bt.value for bt in BackendType]:
            event.add_status(
                ops.BlockedStatus(
                    f"Invalid backend-type: {backend_type}. "
                    "Use 'storage-class', 'native-nfs', or 'hostpath'"
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

        elif backend_type == BackendType.HOSTPATH.value and not self.config.get("hostpath"):
            event.add_status(ops.BlockedStatus("hostpath not configured"))

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

        delete_permission_check_job(self.k8s, self.model.name, self._pvc_name)

        self.k8s.delete(PersistentVolumeClaim, self._pvc_name, self.model.name)
        logger.info("Deleted PVC %s", self._pvc_name)

        backend_type = self.config.get("backend-type")
        if backend_type in (BackendType.NATIVE_NFS.value, BackendType.HOSTPATH.value):
            self.k8s.delete(PersistentVolume, self._pv_name, namespace=None)
            logger.info("Deleted PV %s", self._pv_name)


if __name__ == "__main__":
    ops.main(CharmarrStorageCharm)
