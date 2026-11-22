# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for the Prowlarr API client."""

import json

import httpx

from _prowlarr import ProwlarrApiClient


def _client_with_transport(handler) -> ProwlarrApiClient:
    client = ProwlarrApiClient("http://localhost:9696/prowlarr-k8s", "testkey")
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"X-Api-Key": "testkey"},
    )
    return client


def test_sync_application_indexers_posts_forced_command():
    """The forced ApplicationIndexerSync command hits the v1 command endpoint."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"name": "ApplicationIndexerSync"})

    with _client_with_transport(handler) as client:
        client.sync_application_indexers()

    assert captured["url"] == "http://localhost:9696/prowlarr-k8s/api/v1/command"
    assert captured["json"] == {"name": "ApplicationIndexerSync", "forceSync": True}


def test_sync_application_indexers_can_disable_force():
    """force=False is passed through for callers that want a plain sync."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"name": "ApplicationIndexerSync"})

    with _client_with_transport(handler) as client:
        client.sync_application_indexers(force=False)

    assert captured["json"] == {"name": "ApplicationIndexerSync", "forceSync": False}
