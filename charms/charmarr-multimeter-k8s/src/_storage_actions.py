# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Storage-related action handlers for integration testing."""

import ops
from lightkube import ApiError
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import PersistentVolume, PersistentVolumeClaim

from charmarr_lib.krm import K8sResourceManager


def handle_get_pvc(event: ops.ActionEvent, k8s: K8sResourceManager) -> None:
    """Return PVC details."""
    namespace = event.params["namespace"]
    name = event.params["name"]
    try:
        pvc = k8s.get(PersistentVolumeClaim, name, namespace)
        phase = pvc.status.phase if pvc.status else None
        event.set_results(
            {
                "storage-class": pvc.spec.storageClassName or "",
                "access-modes": ",".join(pvc.spec.accessModes or []),
                "capacity": pvc.spec.resources.requests.get("storage", "")
                if pvc.spec.resources
                else "",
                "volume-name": pvc.spec.volumeName or "",
                "phase": phase or "",
            }
        )
    except ApiError as e:
        event.fail(f"Failed to get PVC: {e}")


def handle_get_pv(event: ops.ActionEvent, k8s: K8sResourceManager) -> None:
    """Return PV details."""
    name = event.params["name"]
    try:
        pv = k8s.get(PersistentVolume, name, namespace=None)
        phase = pv.status.phase if pv.status else None
        nfs_server = ""
        nfs_path = ""
        hostpath = ""
        if pv.spec.nfs:
            nfs_server = pv.spec.nfs.server or ""
            nfs_path = pv.spec.nfs.path or ""
        if pv.spec.hostPath:
            hostpath = pv.spec.hostPath.path or ""
        event.set_results(
            {
                "capacity": pv.spec.capacity.get("storage", "") if pv.spec.capacity else "",
                "access-modes": ",".join(pv.spec.accessModes or []),
                "nfs-server": nfs_server,
                "nfs-path": nfs_path,
                "hostpath": hostpath,
                "reclaim-policy": pv.spec.persistentVolumeReclaimPolicy or "",
                "phase": phase or "",
            }
        )
    except ApiError as e:
        event.fail(f"Failed to get PV: {e}")


def handle_get_mounts(event: ops.ActionEvent, container: ops.Container) -> None:
    """Return list of mount paths in the workload container."""
    try:
        if not container.can_connect():
            event.fail("Cannot connect to container")
            return
        process = container.exec(["cat", "/proc/mounts"])
        output, _ = process.wait_output()
        mounts = [line.split()[1] for line in output.strip().split("\n") if line]
        event.set_results({"mounts": ",".join(mounts)})
    except Exception as e:
        event.fail(f"Failed to get mounts: {e}")


def handle_get_security_context(
    event: ops.ActionEvent,
    k8s: K8sResourceManager,
    statefulset_name: str,
    namespace: str,
) -> None:
    """Return SecurityContext from a StatefulSet's pod spec."""
    try:
        sts = k8s.get(StatefulSet, statefulset_name, namespace)
        if sts.spec is None or sts.spec.template.spec is None:
            event.fail("StatefulSet has no pod spec")
            return

        security_context = sts.spec.template.spec.securityContext
        if security_context is None or security_context.fsGroup is None:
            event.set_results({"configured": "false"})
            return

        event.set_results(
            {
                "configured": "true",
                "fs-group": str(security_context.fsGroup),
            }
        )
    except ApiError as e:
        event.fail(f"Failed to get StatefulSet: {e}")
