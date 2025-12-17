#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr Storage Charm - workload-less charm for shared PVC management."""

import logging
from enum import Enum

import ops

from charmarr_lib.core import observe_events, reconcilable_events_k8s_workloadless
from charmarr_lib.core.interfaces import MediaStorageProvider

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

        observe_events(self, reconcilable_events_k8s_workloadless, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile desired state with actual K8s state."""
        if not self._is_config_valid():
            return

        # TODO: Implement PVC management
        # TODO: Publish relation data

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

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect unit statuses from all components."""
        self._check_config_status(event)

        if self._is_config_valid():
            event.add_status(ops.ActiveStatus("Storage scaffold ready"))

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
