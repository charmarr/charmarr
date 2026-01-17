# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Helper functions specific to charmarr-storage-k8s integration tests."""

import logging
from pathlib import Path
from typing import Any

import jubilant
from pydantic import BaseModel
from pytest_jubilant import pack

logger = logging.getLogger(__name__)

CHARM_DIR = Path(__file__).parent.parent.parent


class PVCData(BaseModel):
    """PVC data returned from get-pvc action."""

    storage_class: str
    access_modes: list[str]
    capacity: str
    volume_name: str
    phase: str


class PVData(BaseModel):
    """PV data returned from get-pv action."""

    capacity: str
    access_modes: list[str]
    nfs_server: str
    nfs_path: str
    hostpath: str
    reclaim_policy: str
    phase: str


def pack_storage_charm() -> Path:
    """Pack the storage charm and return path to .charm file."""
    logger.info("Packing charm from %s", CHARM_DIR)
    return pack(CHARM_DIR)


def deploy_storage_charm(
    juju: jubilant.Juju,
    charm_path: Path,
    backend_type: str,
    config: dict[str, Any],
) -> None:
    """Deploy charmarr-storage charm with specified backend."""
    full_config = {"backend-type": backend_type, **config}
    logger.info("Deploying charmarr-storage with config: %s", full_config)

    juju.deploy(
        str(charm_path),
        app="charmarr-storage",
        trust=True,
        config={k: str(v) for k, v in full_config.items()},
    )


def get_pvc(juju: jubilant.Juju, namespace: str, name: str) -> PVCData | None:
    """Get a PVC from Kubernetes via multimeter action."""
    try:
        result = juju.run(
            "charmarr-multimeter/0", "get-pvc", {"namespace": namespace, "name": name}
        )
        return PVCData(
            storage_class=result.results.get("storage-class", ""),
            access_modes=result.results.get("access-modes", "").split(","),
            capacity=result.results.get("capacity", ""),
            volume_name=result.results.get("volume-name", ""),
            phase=result.results.get("phase", ""),
        )
    except Exception as e:
        logger.warning("Failed to get PVC: %s", e)
        return None


def get_pv(juju: jubilant.Juju, name: str) -> PVData | None:
    """Get a PV from Kubernetes via multimeter action."""
    try:
        result = juju.run("charmarr-multimeter/0", "get-pv", {"name": name})
        return PVData(
            capacity=result.results.get("capacity", ""),
            access_modes=result.results.get("access-modes", "").split(","),
            nfs_server=result.results.get("nfs-server", ""),
            nfs_path=result.results.get("nfs-path", ""),
            hostpath=result.results.get("hostpath", ""),
            reclaim_policy=result.results.get("reclaim-policy", ""),
            phase=result.results.get("phase", ""),
        )
    except Exception as e:
        logger.warning("Failed to get PV: %s", e)
        return None


def get_pod_mounts(juju: jubilant.Juju, app_name: str) -> list[str]:
    """Get list of mount paths for an app's workload container via action."""
    try:
        result = juju.run(f"{app_name}/0", "get-mounts")
        mounts_str = result.results.get("mounts", "")
        return mounts_str.split(",") if mounts_str else []
    except Exception as e:
        logger.warning("Failed to get mounts: %s", e)
        return []
