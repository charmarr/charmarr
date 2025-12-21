# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for CharmarrMultimeterCharm."""

import ops
from ops.testing import Relation, State

from charmarr_lib.core.interfaces import (
    MediaStorageProviderData,
    MediaStorageRequirerData,
)


def test_active_status_no_relations(ctx):
    """Charm is active with no relations."""
    state = ctx.run(ctx.on.start(), State(leader=True))
    assert state.unit_status == ops.ActiveStatus("Ready (no relations)")


def test_non_leader_standby_status(ctx):
    """Non-leader unit shows standby status."""
    state = ctx.run(ctx.on.start(), State(leader=False))
    assert state.unit_status == ops.ActiveStatus("Standby (leader manages relations)")


def test_publishes_media_storage_requirer_data(ctx):
    """Charm publishes requirer data when media-storage relation exists."""
    relation = Relation(endpoint="media-storage", interface="media-storage")
    state_in = State(leader=True, relations=[relation])

    state_out = ctx.run(ctx.on.relation_joined(relation), state_in)

    relation_out = state_out.get_relations("media-storage")[0]
    assert "config" in relation_out.local_app_data
    data = MediaStorageRequirerData.model_validate_json(relation_out.local_app_data["config"])
    assert data.instance_name == "charmarr-multimeter-k8s"


def test_counts_connected_providers(ctx):
    """Charm shows count of connected providers in status."""
    provider_data = MediaStorageProviderData(pvc_name="charmarr-shared")
    relation = Relation(
        endpoint="media-storage",
        interface="media-storage",
        remote_app_data={"config": provider_data.model_dump_json()},
    )
    state_in = State(leader=True, relations=[relation])

    state_out = ctx.run(ctx.on.relation_changed(relation), state_in)

    assert state_out.unit_status == ops.ActiveStatus("Connected to 1 provider(s)")


def test_non_leader_does_not_publish(ctx):
    """Non-leader unit does not publish relation data."""
    relation = Relation(endpoint="media-storage", interface="media-storage")
    state_in = State(leader=False, relations=[relation])

    state_out = ctx.run(ctx.on.relation_joined(relation), state_in)

    relation_out = state_out.get_relations("media-storage")[0]
    assert "config" not in relation_out.local_app_data
