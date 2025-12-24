# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for CharmarrMultimeterCharm."""

from unittest.mock import MagicMock

import ops
from ops.testing import Relation, State

from charmarr_lib.core.interfaces import (
    MediaStorageProviderData,
    MediaStorageRequirerData,
)
from charmarr_lib.vpn.interfaces import VPNGatewayProviderData, VPNGatewayRequirerData


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


def test_get_pvc_action_returns_pvc_details(ctx, mock_k8s):
    """get-pvc action returns PVC details from Kubernetes."""
    mock_pvc = MagicMock()
    mock_pvc.spec.storageClassName = "microk8s-hostpath"
    mock_pvc.spec.accessModes = ["ReadWriteOnce"]
    mock_pvc.spec.resources.requests.get.return_value = "1Gi"
    mock_pvc.spec.volumeName = "pvc-12345"
    mock_pvc.status.phase = "Bound"
    mock_k8s.return_value.get.return_value = mock_pvc

    ctx.run(
        ctx.on.action("get-pvc", params={"namespace": "storage-test", "name": "charmarr-shared"}),
        State(leader=True),
    )

    mock_k8s.return_value.get.assert_called_once()


def test_get_pv_action_returns_pv_details(ctx, mock_k8s):
    """get-pv action returns PV details from Kubernetes."""
    mock_pv = MagicMock()
    mock_pv.spec.capacity = {"storage": "1Gi"}
    mock_pv.spec.accessModes = ["ReadWriteMany"]
    mock_pv.spec.nfs.server = "192.168.1.100"
    mock_pv.spec.nfs.path = "/export"
    mock_pv.spec.persistentVolumeReclaimPolicy = "Retain"
    mock_pv.status.phase = "Bound"
    mock_k8s.return_value.get.return_value = mock_pv

    ctx.run(
        ctx.on.action("get-pv", params={"name": "charmarr-shared-media-pv"}),
        State(leader=True),
    )

    mock_k8s.return_value.get.assert_called_once()


def test_get_pv_action_handles_non_nfs_pv(ctx, mock_k8s):
    """get-pv action handles PVs without NFS config."""
    mock_pv = MagicMock()
    mock_pv.spec.capacity = {"storage": "1Gi"}
    mock_pv.spec.accessModes = ["ReadWriteOnce"]
    mock_pv.spec.nfs = None
    mock_pv.spec.persistentVolumeReclaimPolicy = "Delete"
    mock_pv.status.phase = "Bound"
    mock_k8s.return_value.get.return_value = mock_pv

    ctx.run(
        ctx.on.action("get-pv", params={"name": "some-pv"}),
        State(leader=True),
    )


def test_deploy_nfs_server_action(ctx, mock_k8s):
    """deploy-nfs-server action deploys mock NFS server."""
    ctx.run(
        ctx.on.action("deploy-nfs-server", params={}),
        State(leader=True),
    )


def test_cleanup_nfs_server_action(ctx, mock_k8s):
    """cleanup-nfs-server action removes mock NFS server."""
    ctx.run(
        ctx.on.action("cleanup-nfs-server", params={}),
        State(leader=True),
    )


def test_get_mounts_action_returns_mounts(ctx, mock_k8s):
    """get-mounts action returns mount paths from container."""
    from ops.testing import Container, Exec

    container = Container(
        name="multimeter",
        can_connect=True,
        execs={
            Exec(
                command_prefix=["cat", "/proc/mounts"],
                return_code=0,
                stdout="rootfs / rootfs rw 0 0\n/dev/vda1 /data ext4 rw 0 0\n",
            )
        },
    )
    ctx.run(
        ctx.on.action("get-mounts", params={}),
        State(leader=True, containers=[container]),
    )


def test_publishes_vpn_gateway_requirer_data(ctx):
    """Charm publishes requirer data when vpn-gateway relation exists."""
    relation = Relation(endpoint="vpn-gateway", interface="vpn-gateway")
    state_in = State(leader=True, relations=[relation])

    state_out = ctx.run(ctx.on.relation_joined(relation), state_in)

    relation_out = state_out.get_relations("vpn-gateway")[0]
    assert "config" in relation_out.local_app_data
    data = VPNGatewayRequirerData.model_validate_json(relation_out.local_app_data["config"])
    assert data.instance_name == "charmarr-multimeter-k8s"


def test_reconcile_vpn_when_gateway_ready(ctx):
    """Charm reconciles VPN client when gateway is ready and connected."""
    from unittest.mock import patch

    provider_data = VPNGatewayProviderData(
        gateway_dns_name="gluetun.vpn-gateway.svc.cluster.local",
        cluster_cidrs="10.1.0.0/16,10.152.183.0/24",
        cluster_dns_ip="10.152.183.10",
        vpn_connected=True,
        external_ip="185.112.34.56",
        instance_name="gluetun",
    )
    relation = Relation(
        endpoint="vpn-gateway",
        interface="vpn-gateway",
        remote_app_data={"config": provider_data.model_dump_json()},
    )
    state_in = State(leader=True, relations=[relation])

    with patch("charm.reconcile_gateway_client") as mock_gw_client:
        ctx.run(ctx.on.relation_changed(relation), state_in)
        mock_gw_client.assert_called_once()
        call_kwargs = mock_gw_client.call_args.kwargs
        assert call_kwargs["killswitch"] is True
        assert call_kwargs["data"].vpn_connected is True


def test_reconcile_vpn_when_vpn_not_connected(ctx):
    """Charm reconciles VPN client even when VPN is not connected."""
    from unittest.mock import patch

    provider_data = VPNGatewayProviderData(
        gateway_dns_name="gluetun.vpn-gateway.svc.cluster.local",
        cluster_cidrs="10.1.0.0/16,10.152.183.0/24",
        cluster_dns_ip="10.152.183.10",
        vpn_connected=False,
        instance_name="gluetun",
    )
    relation = Relation(
        endpoint="vpn-gateway",
        interface="vpn-gateway",
        remote_app_data={"config": provider_data.model_dump_json()},
    )
    state_in = State(leader=True, relations=[relation])

    with patch("charm.reconcile_gateway_client") as mock_gw_client:
        ctx.run(ctx.on.relation_changed(relation), state_in)
        mock_gw_client.assert_called_once()
        call_kwargs = mock_gw_client.call_args.kwargs
        assert call_kwargs["data"].vpn_connected is False
