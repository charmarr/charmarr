#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr Multimeter - test utility charm for validating interface providers."""

import ops

from charmarr_lib.core import (
    MediaManager,
    RequestManager,
    observe_events,
    reconcilable_events_k8s_workloadless,
)
from charmarr_lib.core.interfaces import (
    DownloadClientRequirer,
    DownloadClientRequirerData,
    MediaIndexerRequirer,
    MediaIndexerRequirerData,
    MediaManagerRequirer,
    MediaManagerRequirerData,
    MediaStorageRequirer,
    MediaStorageRequirerData,
)
from charmarr_lib.vpn.interfaces import VPNGatewayRequirer, VPNGatewayRequirerData


class CharmarrMultimeterCharm(ops.CharmBase):
    """Test utility charm implementing requirer side of all Charmarr interfaces."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        self._media_storage = MediaStorageRequirer(self, "media-storage")
        self._media_indexer = MediaIndexerRequirer(self, "media-indexer")
        self._download_client = DownloadClientRequirer(self, "download-client")
        self._media_manager = MediaManagerRequirer(self, "media-manager")
        self._vpn_gateway = VPNGatewayRequirer(self, "vpn-gateway")

        observe_events(self, reconcilable_events_k8s_workloadless, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    def _reconcile(self, event: ops.EventBase) -> None:
        """Publish requirer data to all connected providers."""
        if not self.unit.is_leader():
            return

        instance_name = self.app.name

        if self.model.get_relation("media-storage"):
            self._media_storage.publish_data(MediaStorageRequirerData(instance_name=instance_name))

        if self.model.get_relation("media-indexer"):
            self._media_indexer.publish_data(
                MediaIndexerRequirerData(
                    api_url=f"http://{instance_name}:8080",
                    api_key_secret_id="placeholder",
                    manager=MediaManager.RADARR,
                    instance_name=instance_name,
                )
            )

        if self.model.get_relation("download-client"):
            self._download_client.publish_data(
                DownloadClientRequirerData(
                    manager=MediaManager.RADARR,
                    instance_name=instance_name,
                )
            )

        if self.model.get_relation("media-manager"):
            self._media_manager.publish_data(
                MediaManagerRequirerData(
                    requester=RequestManager.OVERSEERR,
                    instance_name=instance_name,
                )
            )

        if self.model.get_relation("vpn-gateway"):
            self._vpn_gateway.publish_data(VPNGatewayRequirerData(instance_name=instance_name))

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect unit status based on connected relations."""
        if not self.unit.is_leader():
            event.add_status(ops.ActiveStatus("Standby (leader manages relations)"))
            return

        connected = self._count_connected_relations()
        if connected == 0:
            event.add_status(ops.ActiveStatus("Ready (no relations)"))
        else:
            event.add_status(ops.ActiveStatus(f"Connected to {connected} provider(s)"))

    def _count_connected_relations(self) -> int:
        """Count number of relations with provider data available."""
        count = 0
        if self._media_storage.is_ready():
            count += 1
        if self._media_indexer.get_provider_data() is not None:
            count += 1
        if self._download_client.get_providers():
            count += 1
        if self._media_manager.get_providers():
            count += 1
        if self._vpn_gateway.get_gateway() is not None:
            count += 1
        return count


if __name__ == "__main__":
    ops.main(CharmarrMultimeterCharm)
