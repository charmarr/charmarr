"""Hostpath backend for charmarr-storage-k8s charm."""

import logging

from lightkube.models.core_v1 import HostPathVolumeSource, PersistentVolumeSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import PersistentVolume

from charmarr_lib.core import K8sResourceManager

logger = logging.getLogger(__name__)


def create_hostpath_pv(
    k8s: K8sResourceManager,
    pv_name: str,
    hostpath: str,
    size: str,
    access_mode: str,
) -> None:
    """Create a hostPath-backed PersistentVolume."""
    pv = PersistentVolume(
        metadata=ObjectMeta(name=pv_name),
        spec=PersistentVolumeSpec(
            capacity={"storage": size},
            accessModes=[access_mode],
            persistentVolumeReclaimPolicy="Retain",
            hostPath=HostPathVolumeSource(path=hostpath, type="Directory"),
        ),
    )

    logger.info("Creating hostPath PV %s with path %s", pv_name, hostpath)
    k8s.apply(pv)


def reconcile_existing_hostpath_pv(
    k8s: K8sResourceManager,
    pv: PersistentVolume,
    pv_name: str,
    hostpath: str,
    size: str,
    access_mode: str,
) -> None:
    """Reconcile an existing hostpath PV with current config.

    Handles Released PVs (clears claimRef) and config drift.
    """
    needs_update = False
    reason = ""

    if pv.status and pv.status.phase == "Released":
        logger.info("PV %s is Released, clearing claimRef for reuse", pv_name)
        needs_update = True
        reason = "Released state"

    if pv.spec and pv.spec.hostPath and pv.spec.hostPath.path != hostpath:
        logger.info(
            "PV %s hostPath changed (%s -> %s)",
            pv_name,
            pv.spec.hostPath.path,
            hostpath,
        )
        needs_update = True
        reason = "config drift"

    current_size = pv.spec.capacity.get("storage", "") if pv.spec and pv.spec.capacity else ""
    if current_size and current_size != size:
        logger.info("PV %s size changed (%s -> %s)", pv_name, current_size, size)
        needs_update = True
        reason = "size change"

    if not needs_update:
        return

    logger.info("Updating PV %s due to %s", pv_name, reason)
    updated_pv = PersistentVolume(
        metadata=ObjectMeta(name=pv_name),
        spec=PersistentVolumeSpec(
            capacity={"storage": size},
            accessModes=[access_mode],
            persistentVolumeReclaimPolicy="Retain",
            hostPath=HostPathVolumeSource(path=hostpath, type="Directory"),
            claimRef=None,
        ),
    )
    k8s.apply(updated_pv, force=True)
