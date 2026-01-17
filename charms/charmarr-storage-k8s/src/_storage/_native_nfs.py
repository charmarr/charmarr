"""Native NFS backend for charmarr-storage-k8s charm."""

import logging

from lightkube.models.core_v1 import NFSVolumeSource, PersistentVolumeSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import PersistentVolume

from charmarr_lib.core import K8sResourceManager

logger = logging.getLogger(__name__)


def create_nfs_pv(
    k8s: K8sResourceManager,
    pv_name: str,
    nfs_server: str,
    nfs_path: str,
    size: str,
    access_mode: str,
) -> None:
    """Create an NFS-backed PersistentVolume."""
    pv = PersistentVolume(
        metadata=ObjectMeta(name=pv_name),
        spec=PersistentVolumeSpec(
            capacity={"storage": size},
            accessModes=[access_mode],
            persistentVolumeReclaimPolicy="Retain",
            nfs=NFSVolumeSource(server=nfs_server, path=nfs_path),
        ),
    )

    logger.info("Creating NFS PV %s with server %s, path %s", pv_name, nfs_server, nfs_path)
    k8s.apply(pv)


def reconcile_existing_nfs_pv(
    k8s: K8sResourceManager,
    pv: PersistentVolume,
    pv_name: str,
    nfs_server: str,
    nfs_path: str,
    size: str,
    access_mode: str,
) -> None:
    """Reconcile an existing NFS PV with current config.

    Handles Released PVs (clears claimRef) and config drift.
    """
    needs_update = False
    reason = ""

    if pv.status and pv.status.phase == "Released":
        logger.info("PV %s is Released, clearing claimRef for reuse", pv_name)
        needs_update = True
        reason = "Released state"

    if (
        pv.spec
        and pv.spec.nfs
        and (pv.spec.nfs.server != nfs_server or pv.spec.nfs.path != nfs_path)
    ):
        logger.info(
            "PV %s NFS config changed (%s:%s -> %s:%s)",
            pv_name,
            pv.spec.nfs.server,
            pv.spec.nfs.path,
            nfs_server,
            nfs_path,
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
            nfs=NFSVolumeSource(server=nfs_server, path=nfs_path),
            claimRef=None,
        ),
    )
    k8s.apply(updated_pv, force=True)
