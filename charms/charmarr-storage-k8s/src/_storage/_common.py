"""Common storage utilities shared across backends."""

import logging

from lightkube import ApiError
from lightkube.models.core_v1 import PersistentVolumeClaimSpec, VolumeResourceRequirements
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import PersistentVolume, PersistentVolumeClaim

from charmarr_lib.core import K8sResourceManager

logger = logging.getLogger(__name__)


def get_pv(k8s: K8sResourceManager, pv_name: str) -> PersistentVolume | None:
    """Get a PersistentVolume by name, or None if not found."""
    try:
        return k8s.get(PersistentVolume, pv_name, namespace=None)
    except ApiError as e:
        if e.status.code == 404:
            return None
        raise


def get_pvc(
    k8s: K8sResourceManager, pvc_name: str, namespace: str
) -> PersistentVolumeClaim | None:
    """Get a PersistentVolumeClaim by name, or None if not found."""
    try:
        return k8s.get(PersistentVolumeClaim, pvc_name, namespace)
    except ApiError as e:
        if e.status.code == 404:
            return None
        raise


def create_static_pvc(
    k8s: K8sResourceManager,
    pvc_name: str,
    pv_name: str,
    namespace: str,
    size: str,
    access_mode: str,
) -> None:
    """Create a PVC that binds to a static PV (native-nfs or hostpath)."""
    pvc = PersistentVolumeClaim(
        metadata=ObjectMeta(name=pvc_name, namespace=namespace),
        spec=PersistentVolumeClaimSpec(
            storageClassName="",
            accessModes=[access_mode],
            resources=VolumeResourceRequirements(requests={"storage": size}),
            volumeName=pv_name,
        ),
    )

    logger.info("Creating PVC %s bound to PV %s", pvc_name, pv_name)
    k8s.apply(pvc)


def log_static_pv_size_mismatch(
    pvc: PersistentVolumeClaim, pvc_name: str, desired_size: str
) -> None:
    """Log info if PVC size differs from config.

    For static PVs (native-nfs, hostpath), PVC size is informational only.
    Actual capacity is determined by the underlying storage, not the PVC.
    """
    current_requests = pvc.spec.resources.requests if pvc.spec and pvc.spec.resources else {}
    current_size = (current_requests or {}).get("storage", "")

    if current_size and current_size != desired_size:
        logger.info(
            "PVC %s shows %s but config is %s. For static PVs, this is cosmetic - "
            "actual capacity is determined by underlying storage",
            pvc_name,
            current_size,
            desired_size,
        )
