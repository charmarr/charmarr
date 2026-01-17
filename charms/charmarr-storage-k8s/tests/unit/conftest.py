# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for unit tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lightkube import ApiError
from lightkube.models.batch_v1 import JobStatus
from lightkube.models.core_v1 import (
    NFSVolumeSource,
    PersistentVolumeClaimSpec,
    PersistentVolumeClaimStatus,
    PersistentVolumeSpec,
    PersistentVolumeStatus,
    VolumeResourceRequirements,
)
from lightkube.models.meta_v1 import ObjectMeta, Status
from lightkube.resources.batch_v1 import Job
from lightkube.resources.core_v1 import PersistentVolume, PersistentVolumeClaim
from ops.testing import Context

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from charm import CharmarrStorageCharm


@pytest.fixture
def ctx() -> Context[CharmarrStorageCharm]:
    """Create a testing context for CharmarrStorageCharm."""
    return Context(CharmarrStorageCharm)


@pytest.fixture
def mock_k8s():
    """Create a mock K8sResourceManager that handles PVC, PV, and Job resources."""
    with patch("charm.K8sResourceManager") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        # Store custom configurations that tests can set
        mock_instance._custom_get_return = None
        mock_instance._custom_get_side_effect = None

        def smart_get(resource_type, name, namespace=None):
            # Job resources return a passed job by default (permission check succeeded)
            if resource_type == Job:
                return make_passed_job()
            # If test set a custom side_effect, use it
            if mock_instance._custom_get_side_effect is not None:
                return mock_instance._custom_get_side_effect(resource_type, name, namespace)
            # If test set a custom return value, use it
            if mock_instance._custom_get_return is not None:
                return mock_instance._custom_get_return
            return MagicMock()

        mock_instance.get.side_effect = smart_get
        yield mock_instance


def make_api_error_404() -> ApiError:
    """Create a 404 ApiError for testing PVC not found."""
    response = MagicMock()
    response.status_code = 404
    response.json.return_value = {"code": 404, "message": "not found"}
    error = ApiError(response=response)
    error.status = Status(code=404, message="not found")
    return error


def make_pvc(phase: str, size: str = "100Gi") -> PersistentVolumeClaim:
    """Create a mock PVC with the given phase."""
    return PersistentVolumeClaim(
        metadata=ObjectMeta(name="charmarr-shared-media", namespace="test-model"),
        spec=PersistentVolumeClaimSpec(
            storageClassName="local-path",
            accessModes=["ReadWriteMany"],
            resources=VolumeResourceRequirements(requests={"storage": size}),
        ),
        status=PersistentVolumeClaimStatus(phase=phase),
    )


def make_nfs_pv(phase: str, size: str = "100Gi") -> PersistentVolume:
    """Create a mock NFS PV with the given phase."""
    return PersistentVolume(
        metadata=ObjectMeta(name="charmarr-shared-media-pv"),
        spec=PersistentVolumeSpec(
            capacity={"storage": size},
            accessModes=["ReadWriteMany"],
            persistentVolumeReclaimPolicy="Retain",
            nfs=NFSVolumeSource(server="192.168.1.100", path="/mnt/media"),
        ),
        status=PersistentVolumeStatus(phase=phase),
    )


def make_nfs_pvc(phase: str, size: str = "100Gi") -> PersistentVolumeClaim:
    """Create a mock NFS PVC with the given phase."""
    return PersistentVolumeClaim(
        metadata=ObjectMeta(name="charmarr-shared-media", namespace="test-model"),
        spec=PersistentVolumeClaimSpec(
            storageClassName="",
            accessModes=["ReadWriteMany"],
            resources=VolumeResourceRequirements(requests={"storage": size}),
            volumeName="charmarr-shared-media-pv",
        ),
        status=PersistentVolumeClaimStatus(phase=phase),
    )


def make_hostpath_pv(phase: str, size: str = "100Gi") -> PersistentVolume:
    """Create a mock hostPath PV with the given phase."""
    from lightkube.models.core_v1 import HostPathVolumeSource

    return PersistentVolume(
        metadata=ObjectMeta(name="charmarr-shared-media-pv"),
        spec=PersistentVolumeSpec(
            capacity={"storage": size},
            accessModes=["ReadWriteMany"],
            persistentVolumeReclaimPolicy="Retain",
            hostPath=HostPathVolumeSource(path="/media", type="Directory"),
        ),
        status=PersistentVolumeStatus(phase=phase),
    )


def make_hostpath_pvc(phase: str, size: str = "100Gi") -> PersistentVolumeClaim:
    """Create a mock hostPath PVC with the given phase."""
    return PersistentVolumeClaim(
        metadata=ObjectMeta(name="charmarr-shared-media", namespace="test-model"),
        spec=PersistentVolumeClaimSpec(
            storageClassName="",
            accessModes=["ReadWriteMany"],
            resources=VolumeResourceRequirements(requests={"storage": size}),
            volumeName="charmarr-shared-media-pv",
        ),
        status=PersistentVolumeClaimStatus(phase=phase),
    )


def make_passed_job() -> Job:
    """Create a mock Job that has succeeded (permission check passed)."""
    return Job(
        metadata=ObjectMeta(
            name="charmarr-permission-check-charmarr-shared-medi",
            namespace="test-model",
            labels={
                "charmarr.io/puid": "1000",
                "charmarr.io/pgid": "1000",
            },
        ),
        status=JobStatus(succeeded=1),
    )
