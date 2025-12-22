# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Common step definitions for charmarr-storage-k8s integration tests."""

import logging
from pathlib import Path
from typing import Any

import jubilant
import pytest
from pytest_bdd import given, parsers, then, when
from tenacity import retry, stop_after_attempt, wait_exponential

from charmarr_lib.testing import deploy_multimeter, get_app_relation_data, wait_for_active_idle
from tests.integration.helpers import deploy_storage_charm, pack_storage_charm

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def charm_path() -> Path:
    """Pack the charm once per test module."""
    return pack_storage_charm()


@pytest.fixture(scope="module")
def storage_config() -> dict[str, Any]:
    """Store storage charm config for the test module."""
    return {}


@given("the charmarr-storage charm is deployed with storage-class backend")
def deploy_storage_class_backend(
    juju: jubilant.Juju, charm_path: Path, storage_config: dict[str, Any]
):
    """Deploy charmarr-storage with storage-class backend."""
    config = {
        "storage-class": "microk8s-hostpath",
        "size": "1Gi",
        "access-mode": "ReadWriteOnce",
        "puid": 1000,
        "pgid": 1000,
        "cleanup-on-remove": True,
    }
    storage_config.update(config)
    status = juju.status()
    if "charmarr-storage" in status.apps:
        return
    deploy_storage_charm(juju, charm_path, "storage-class", config)
    wait_for_active_idle(juju)


@given("the charmarr-storage charm is deployed with native-nfs backend")
def deploy_native_nfs_backend(
    juju: jubilant.Juju,
    charm_path: Path,
    storage_config: dict[str, Any],
    nfs_server_ip: str,
):
    """Deploy charmarr-storage with native-nfs backend using mock NFS server."""
    config = {
        "nfs-server": nfs_server_ip,
        "nfs-path": "/",
        "size": "1Gi",
        "puid": 1000,
        "pgid": 1000,
        "cleanup-on-remove": True,
    }
    storage_config.update(config)
    status = juju.status()
    if "charmarr-storage" in status.apps:
        return
    deploy_storage_charm(juju, charm_path, "native-nfs", config)
    wait_for_active_idle(juju)


@given("the charmarr-multimeter charm is deployed")
def deploy_multimeter_charm(juju: jubilant.Juju):
    """Deploy charmarr-multimeter from Charmhub."""
    status = juju.status()
    if "charmarr-multimeter" not in status.apps:
        deploy_multimeter(juju)
        wait_for_active_idle(juju)


@given("charmarr-multimeter is related to charmarr-storage via media-storage")
@when("charmarr-multimeter is related to charmarr-storage via media-storage")
def integrate_multimeter_storage(juju: jubilant.Juju):
    """Integrate multimeter with storage via media-storage relation."""
    status = juju.status()
    app = status.apps.get("charmarr-multimeter")
    if app and "media-storage" in app.relations:
        return
    juju.integrate("charmarr-multimeter:media-storage", "charmarr-storage:media-storage")
    wait_for_active_idle(juju)


@when(parsers.parse('the storage charm config "{key}" is set to "{value}"'))
def set_storage_config(juju: jubilant.Juju, key: str, value: str, storage_config: dict[str, Any]):
    """Set a config option on the storage charm."""
    juju.cli("config", "charmarr-storage", f"{key}={value}")
    storage_config[key] = value
    wait_for_active_idle(juju)


@then("the storage charm should be active")
def storage_charm_active(juju: jubilant.Juju):
    """Verify storage charm is active."""
    status = juju.status()
    app = status.apps["charmarr-storage"]
    assert app.app_status.current == "active", (
        f"Storage charm status: {app.app_status.current} - {app.app_status.message}"
    )


@then("the multimeter charm should be active")
def multimeter_charm_active(juju: jubilant.Juju):
    """Verify multimeter charm is active."""
    status = juju.status()
    app = status.apps["charmarr-multimeter"]
    assert app.app_status.current == "active", (
        f"Multimeter charm status: {app.app_status.current} - {app.app_status.message}"
    )


# PVC steps common to both backends


@then(parsers.parse('a PVC named "{name}" should exist in the model namespace'))
def pvc_exists(juju: jubilant.Juju, name: str):
    """Verify PVC exists."""
    from tests.integration.helpers import get_pvc

    @retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, min=2, max=10))
    def check_exists():
        assert get_pvc(juju, juju.model, name) is not None, f"PVC {name} not found"

    check_exists()


@then(parsers.parse('the PVC "{name}" should be in "{phase}" phase'))
def pvc_phase(juju: jubilant.Juju, name: str, phase: str):
    """Verify PVC is in the expected phase."""
    from tests.integration.helpers import get_pvc

    @retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, min=2, max=10))
    def check_phase():
        pvc = get_pvc(juju, juju.model, name)
        assert pvc is not None, f"PVC {name} not found"
        assert pvc.phase == phase, f"PVC {name} phase is {pvc.phase}, expected {phase}"

    check_phase()


# Relation data steps


@then(parsers.parse('the media-storage relation should contain pvc_name "{expected}"'))
def relation_pvc_name(juju: jubilant.Juju, expected: str):
    """Verify relation data contains the expected pvc_name."""
    data = get_app_relation_data(juju, "charmarr-multimeter/0", "media-storage")
    assert data["pvc_name"] == expected


@then(parsers.parse('the media-storage relation should contain mount_path "{expected}"'))
def relation_mount_path(juju: jubilant.Juju, expected: str):
    """Verify relation data contains the expected mount_path."""
    data = get_app_relation_data(juju, "charmarr-multimeter/0", "media-storage")
    assert data["mount_path"] == expected


@then(parsers.parse("the media-storage relation should contain puid {expected:d}"))
def relation_puid(juju: jubilant.Juju, expected: int):
    """Verify relation data contains the expected puid."""
    data = get_app_relation_data(juju, "charmarr-multimeter/0", "media-storage")
    assert data["puid"] == expected


@then(parsers.parse("the media-storage relation should contain pgid {expected:d}"))
def relation_pgid(juju: jubilant.Juju, expected: int):
    """Verify relation data contains the expected pgid."""
    data = get_app_relation_data(juju, "charmarr-multimeter/0", "media-storage")
    assert data["pgid"] == expected


# Mount and unmount steps


@then(parsers.parse('the multimeter pod should have "{path}" mounted'))
def multimeter_has_mount(juju: jubilant.Juju, path: str):
    """Verify multimeter pod has the path mounted."""
    from tests.integration.helpers import get_pod_mounts

    mounts = get_pod_mounts(juju, "charmarr-multimeter")
    assert path in mounts, f"Expected {path} to be mounted, got: {mounts}"


@then(parsers.parse('the multimeter pod should not have "{path}" mounted'))
def multimeter_no_mount(juju: jubilant.Juju, path: str):
    """Verify multimeter pod does not have the path mounted."""
    from tests.integration.helpers import get_pod_mounts

    mounts = get_pod_mounts(juju, "charmarr-multimeter")
    assert path not in mounts, f"Expected {path} not to be mounted, but found it in: {mounts}"


# Relation removal steps


@when("the media-storage relation is removed")
def remove_media_storage_relation(juju: jubilant.Juju):
    """Remove the media-storage relation."""
    juju.cli(
        "remove-relation", "charmarr-multimeter:media-storage", "charmarr-storage:media-storage"
    )
    wait_for_active_idle(juju)


# Cleanup-on-remove config steps


@given(parsers.parse('cleanup-on-remove config is "{value}"'))
def set_cleanup_config(juju: jubilant.Juju, value: str, storage_config: dict[str, Any]):
    """Set cleanup-on-remove config."""
    bool_value = value.lower() == "true"
    juju.cli("config", "charmarr-storage", f"cleanup-on-remove={bool_value}")
    storage_config["cleanup-on-remove"] = bool_value
    wait_for_active_idle(juju)


@when("the storage charm is removed")
def remove_storage_charm(juju: jubilant.Juju):
    """Remove the storage charm."""
    juju.cli("remove-application", "charmarr-storage", "--force", "--no-prompt")
    juju.wait(lambda status: "charmarr-storage" not in status.apps, timeout=120)


@then(parsers.parse('the PVC "{name}" should still exist'))
def pvc_still_exists(juju: jubilant.Juju, name: str):
    """Verify PVC still exists after charm removal."""
    from tests.integration.helpers import get_pvc

    pvc = get_pvc(juju, juju.model, name)
    assert pvc is not None, f"Expected PVC {name} to still exist"


@then(parsers.parse('no PVC named "{name}" should exist'))
def pvc_not_exists(juju: jubilant.Juju, name: str):
    """Verify PVC does not exist."""
    from tests.integration.helpers import get_pvc

    pvc = get_pvc(juju, juju.model, name)
    assert pvc is None, f"Expected PVC {name} to not exist, but it does"


@then(parsers.parse('the PV "{name}" should still exist'))
def pv_still_exists(juju: jubilant.Juju, name: str):
    """Verify PV still exists after charm removal."""
    from tests.integration.helpers import get_pv

    pv = get_pv(juju, name)
    assert pv is not None, f"Expected PV {name} to still exist"


@then(parsers.parse('no PV named "{name}" should exist'))
def pv_not_exists(juju: jubilant.Juju, name: str):
    """Verify PV does not exist."""
    from tests.integration.helpers import get_pv

    pv = get_pv(juju, name)
    assert pv is None, f"Expected PV {name} to not exist, but it does"


# Scale and leader steps


@when(parsers.parse("the storage charm is scaled to {count:d} units"))
def scale_storage_charm(juju: jubilant.Juju, count: int):
    """Scale the storage charm to the specified number of units."""
    juju.cli("add-unit", "charmarr-storage", "-n", str(count - 1))
    wait_for_active_idle(juju)


@then("the leader unit should be active")
def leader_is_active(juju: jubilant.Juju):
    """Verify the leader unit is active."""
    status = juju.status()
    app = status.apps["charmarr-storage"]
    for unit_name, unit in app.units.items():
        if unit.leader:
            assert unit.workload_status.current == "active", (
                f"Leader {unit_name} not active: {unit.workload_status.current}"
            )
            return
    raise AssertionError("No leader unit found")


@then(parsers.parse('non-leader units should show "{message}" in status'))
def non_leader_status(juju: jubilant.Juju, message: str):
    """Verify non-leader units show the expected message in status."""
    status = juju.status()
    app = status.apps["charmarr-storage"]
    for unit_name, unit in app.units.items():
        if not unit.leader:
            assert message in unit.workload_status.message, (
                f"Non-leader {unit_name} status message: {unit.workload_status.message}"
            )


# Resize error handling steps


@then(parsers.parse('the storage charm should be blocked with message containing "{text}"'))
def storage_blocked_with_message(juju: jubilant.Juju, text: str):
    """Verify storage charm is blocked with message containing text."""
    status = juju.status()
    app = status.apps["charmarr-storage"]
    assert app.app_status.current == "blocked", (
        f"Expected blocked status, got: {app.app_status.current}"
    )
    assert text.lower() in app.app_status.message.lower(), (
        f"Expected '{text}' in message, got: {app.app_status.message}"
    )


@when(parsers.parse('the storage charm config "{key}" is set to "{value}" expecting blocked'))
def set_storage_config_expecting_blocked(
    juju: jubilant.Juju, key: str, value: str, storage_config: dict[str, Any]
):
    """Set a config option expecting the charm to become blocked."""
    juju.cli("config", "charmarr-storage", f"{key}={value}")
    storage_config[key] = value
    juju.wait(
        lambda status: status.apps["charmarr-storage"].app_status.current == "blocked",
        timeout=60,
    )


@given("the storage charm is blocked due to resize failure")
def storage_blocked_due_to_resize(juju: jubilant.Juju, storage_config: dict[str, Any]):
    """Ensure storage charm is blocked due to resize failure."""
    juju.cli("config", "charmarr-storage", "size=200Gi")
    storage_config["size"] = "200Gi"
    juju.wait(
        lambda status: status.apps["charmarr-storage"].app_status.current == "blocked",
        timeout=60,
    )


@when('the storage charm config "size" is set to the current PVC size')
def set_size_to_current_pvc(juju: jubilant.Juju, storage_config: dict[str, Any]):
    """Set size config to match the current PVC size."""
    from tests.integration.helpers import get_pvc

    pvc = get_pvc(juju, juju.model, "charmarr-shared-media")
    assert pvc is not None
    current_size = pvc.capacity
    juju.cli("config", "charmarr-storage", f"size={current_size}")
    storage_config["size"] = current_size
    wait_for_active_idle(juju)
