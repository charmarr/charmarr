#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr Storage Charm - workload-less charm for shared PVC management."""

import logging
from enum import Enum

import ops
from lightkube import ApiError
from lightkube.models.core_v1 import (
    PersistentVolumeClaim,
    PersistentVolumeClaimSpec,
    VolumeResourceRequirements,
)
from lightkube.models.meta_v1 import ObjectMeta

from charmarr_lib.core import (
    K8sResourceManager,
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

        observe_events(self, reconcilable_events_k8s_workloadless, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    @property
    def k8s(self) -> K8sResourceManager:
        """Lazily initialize K8s resource manager."""
        if self._k8s is None:
            self._k8s = K8sResourceManager()
        return self._k8s

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile desired state with actual K8s state."""
        if not self.unit.is_leader():
            return

        if not self._is_config_valid():
            return

        backend_type = self.config.get("backend-type")
        if backend_type == BackendType.STORAGE_CLASS.value:
            self._reconcile_storage_class_pvc()
        # native-nfs backend will be implemented in a future task

        self._publish_relation_data()

    def _is_config_valid(self) -> bool:
        """Check if charm configuration is valid."""
        backend_type = self.config.get("backend-type", "")

        if not backend_type or backend_type not in [bt.value for bt in BackendType]:
            return False

        if backend_type == BackendType.STORAGE_CLASS.value:
            return bool(self.config.get("storage-class"))

        if backend_type == BackendType.NATIVE_NFS.value:
            return bool(self.config.get("nfs-server") and self.config.get("nfs-path"))

        return True

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

        if current_size != desired_size:
            logger.info(
                "Updating PVC %s size from %s to %s", self._pvc_name, current_size, desired_size
            )
            patch = {"spec": {"resources": {"requests": {"storage": desired_size}}}}
            self.k8s.patch(PersistentVolumeClaim, self._pvc_name, patch, self.model.name)

    def _get_pvc_phase(self) -> str | None:
        """Get the current PVC phase (Pending, Bound, Lost)."""
        pvc = self._get_pvc()
        if pvc is None or pvc.status is None:
            return None
        return pvc.status.phase

    def _publish_relation_data(self) -> None:
        """Publish storage data to all related applications."""
        pvc_phase = self._get_pvc_phase()
        if pvc_phase != "Bound":
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
            event.add_status(ops.BlockedStatus("native-nfs backend not yet implemented"))
            return

        pvc_phase = self._get_pvc_phase()

        if pvc_phase is None:
            event.add_status(ops.MaintenanceStatus("Creating PVC"))
        elif pvc_phase == "Pending":
            event.add_status(ops.MaintenanceStatus("PVC pending - waiting for volume"))
        elif pvc_phase == "Bound":
            connected = self._storage_provider.get_connected_apps()
            if connected:
                event.add_status(
                    ops.ActiveStatus(f"Storage ready ({len(connected)} apps connected)")
                )
            else:
                event.add_status(ops.ActiveStatus("Storage ready"))
        elif pvc_phase == "Lost":
            event.add_status(ops.BlockedStatus("PVC lost - underlying volume unavailable"))

    def _check_config_status(self, event: ops.CollectStatusEvent) -> None:
        """Check configuration and add relevant statuses."""
        backend_type = self.config.get("backend-type", "")

        if not backend_type:
            event.add_status(ops.BlockedStatus("backend-type not configured"))

        elif backend_type not in [bt.value for bt in BackendType]:
            event.add_status(
                ops.BlockedStatus(
                    f"Invalid backend-type: {backend_type}. Use 'storage-class' or 'native-nfs'"
                )
            )

        elif backend_type == BackendType.STORAGE_CLASS.value:
            if not self.config.get("storage-class"):
                event.add_status(ops.BlockedStatus("storage-class not configured"))

        elif backend_type == BackendType.NATIVE_NFS.value:
            if not self.config.get("nfs-server"):
                event.add_status(ops.BlockedStatus("nfs-server not configured"))
            if not self.config.get("nfs-path"):
                event.add_status(ops.BlockedStatus("nfs-path not configured"))


if __name__ == "__main__":
    ops.main(CharmarrStorageCharm)
