# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for Jellyfin first-run bootstrap and library reconciliation."""

from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Relation, Secret, State

from _jellyfin import VirtualFolder
from charmarr_lib.core import ContentVariant, MediaManager
from charmarr_lib.core.interfaces import MediaManagerProviderData, MediaStorageProviderData

from .conftest import JELLYFIN_CONTAINER


def _storage_relation() -> Relation:
    data = MediaStorageProviderData(pvc_name="charmarr-shared")
    return Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": data.model_dump_json()},
    )


def _manager_relation(
    manager: MediaManager,
    variant: ContentVariant,
    root_folders: list[str],
    instance_name: str = "radarr-hd",
) -> Relation:
    data = MediaManagerProviderData(
        api_url="http://radarr:7878",
        api_key_secret_id="secret:abc",
        manager=manager,
        instance_name=instance_name,
        quality_profiles=[],
        root_folders=root_folders,
        variant=variant,
    )
    return Relation(
        endpoint="media-manager",
        interface="media-manager",
        remote_app_name=instance_name,
        remote_app_data={"config": data.model_dump_json()},
    )


def _api_key_secret(api_key: str = "existing-key") -> Secret:
    return Secret({"api-key": api_key}, label="api-key", owner="app")


def _admin_secret() -> Secret:
    return Secret(
        {"username": "charmarr", "password": "pw"}, label="admin-credentials", owner="app"
    )


@pytest.fixture
def api():
    """Patch the Jellyfin API client and yield the mock instance."""
    with patch("charm.JellyfinApi") as mock_class:
        instance = MagicMock()
        instance.is_ready.return_value = True
        instance.is_setup_complete.return_value = False
        instance.authenticate.return_value = "session-token"
        instance.ensure_api_key.return_value = "minted-key"
        instance.get_virtual_folders.return_value = []
        mock_class.return_value.__enter__.return_value = instance
        yield instance


@pytest.fixture
def reconcile_patches():
    """Stub out the K8s-facing reconcilers the bootstrap path does not exercise."""
    with (
        patch("charm.reconcile_storage_volume"),
        patch("charm.ensure_pebble_user"),
    ):
        yield


def _run(ctx, state: State) -> State:
    return ctx.run(ctx.on.config_changed(), state)


def test_bootstrap_completes_wizard_and_stores_api_key(ctx, mock_k8s, api, reconcile_patches):
    """First run completes the startup wizard and persists the minted API key."""
    state = _run(
        ctx,
        State(leader=True, containers=[JELLYFIN_CONTAINER], relations=[_storage_relation()]),
    )

    api.complete_setup_wizard.assert_called_once()
    api.ensure_api_key.assert_called_once()

    labels = {s.label: s for s in state.secrets}
    assert labels["admin-credentials"].latest_content["username"] == "charmarr"
    assert labels["api-key"].latest_content["api-key"] == "minted-key"


def test_bootstrap_skipped_when_api_key_exists(ctx, mock_k8s, api, reconcile_patches):
    """An existing API key short-circuits the bootstrap."""
    _run(
        ctx,
        State(
            leader=True,
            containers=[JELLYFIN_CONTAINER],
            relations=[_storage_relation()],
            secrets=[_api_key_secret()],
        ),
    )

    api.complete_setup_wizard.assert_not_called()
    api.ensure_api_key.assert_not_called()


def test_bootstrap_resumes_when_wizard_already_completed(ctx, mock_k8s, api, reconcile_patches):
    """An interrupted bootstrap mints the key without rerunning the wizard."""
    api.is_setup_complete.return_value = True

    state = _run(
        ctx,
        State(
            leader=True,
            containers=[JELLYFIN_CONTAINER],
            relations=[_storage_relation()],
            secrets=[_admin_secret()],
        ),
    )

    api.complete_setup_wizard.assert_not_called()
    api.authenticate.assert_called_once_with("charmarr", "pw")
    labels = {s.label: s for s in state.secrets}
    assert labels["api-key"].latest_content["api-key"] == "minted-key"


def test_bootstrap_abandoned_when_set_up_externally(ctx, mock_k8s, api, reconcile_patches):
    """A server set up outside the charm cannot be bootstrapped."""
    api.is_setup_complete.return_value = True

    state = _run(
        ctx,
        State(leader=True, containers=[JELLYFIN_CONTAINER], relations=[_storage_relation()]),
    )

    api.complete_setup_wizard.assert_not_called()
    api.authenticate.assert_not_called()
    assert not [s for s in state.secrets if s.label == "api-key"]


def test_libraries_created_for_each_root_folder(ctx, mock_k8s, api, reconcile_patches):
    """Each media manager root folder becomes a Jellyfin library."""
    _run(
        ctx,
        State(
            leader=True,
            containers=[JELLYFIN_CONTAINER],
            relations=[
                _storage_relation(),
                _manager_relation(MediaManager.RADARR, ContentVariant.UHD, ["/media/movies-4k"]),
            ],
            secrets=[_api_key_secret()],
        ),
    )

    api.create_virtual_folder.assert_called_once_with(
        name="Movies (4K)", collection_type="movies", path="/media/movies-4k"
    )


def test_libraries_skip_existing_paths(ctx, mock_k8s, api, reconcile_patches):
    """Paths already covered by a library are not recreated."""
    api.get_virtual_folders.return_value = [
        VirtualFolder(name="Movies", collection_type="movies", locations=["/media/movies"])
    ]

    _run(
        ctx,
        State(
            leader=True,
            containers=[JELLYFIN_CONTAINER],
            relations=[
                _storage_relation(),
                _manager_relation(
                    MediaManager.RADARR,
                    ContentVariant.STANDARD,
                    ["/media/movies", "/media/movies-extra"],
                ),
            ],
            secrets=[_api_key_secret()],
        ),
    )

    api.create_virtual_folder.assert_called_once_with(
        name="Movies", collection_type="movies", path="/media/movies-extra"
    )


def test_libraries_noop_without_media_manager(ctx, mock_k8s, api, reconcile_patches):
    """No media-manager relation means no libraries are touched."""
    _run(
        ctx,
        State(
            leader=True,
            containers=[JELLYFIN_CONTAINER],
            relations=[_storage_relation()],
            secrets=[_api_key_secret()],
        ),
    )

    api.create_virtual_folder.assert_not_called()
