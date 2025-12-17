# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Fixtures for unit tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lightkube import ApiError
from lightkube.models.core_v1 import (
    PersistentVolumeClaim,
    PersistentVolumeClaimSpec,
    PersistentVolumeClaimStatus,
    VolumeResourceRequirements,
)
from lightkube.models.meta_v1 import ObjectMeta, Status
from ops.testing import Context

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from charm import CharmarrStorageCharm


@pytest.fixture
def ctx() -> Context[CharmarrStorageCharm]:
    """Create a testing context for CharmarrStorageCharm."""
    return Context(CharmarrStorageCharm)


@pytest.fixture
def mock_k8s():
    """Create a mock K8sResourceManager."""
    with patch("charm.K8sResourceManager") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
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
