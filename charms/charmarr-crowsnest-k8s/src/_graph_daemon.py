#!/usr/bin/env python3
# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Detached HTTP server serving the charmarr topology graph in
`nodegraph-api` plugin format.

Usage:
    _graph_daemon.py <port> <data_file>

`data_file` is a JSON file with `{"nodes": [...], "edges": [...]}` written
by the charm reconciler. The server serves:

- ``GET /api/health`` -> "ok"
- ``GET /api/graph/fields`` -> static schema definition
- ``GET /api/graph/data`` -> contents of `<data_file>`

CORS open so the Grafana plugin can fetch cross-origin.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

DATA_FILE = sys.argv[2]

FIELDS = {
    "edges_fields": [
        {"field_name": "id", "type": "string"},
        {"field_name": "source", "type": "string"},
        {"field_name": "target", "type": "string"},
        {"field_name": "mainstat", "type": "string"},
    ],
    "nodes_fields": [
        {"field_name": "id", "type": "string"},
        {"field_name": "title", "type": "string"},
        {"field_name": "mainstat", "type": "string"},
        {"field_name": "arc__bound", "type": "number", "color": "green"},
        {"field_name": "arc__missing", "type": "number", "color": "red"},
        {"field_name": "arc__optional", "type": "number", "color": "yellow"},
        {
            "field_name": "detail__model",
            "type": "string",
            "displayName": "Model",
        },
        {
            "field_name": "detail__missing_required",
            "type": "string",
            "displayName": "Missing required",
        },
        {
            "field_name": "detail__missing_optional",
            "type": "string",
            "displayName": "Missing optional",
        },
    ],
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        del format, args  # silence access logs

    def _send_json(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json(b'"ok"')
            return
        if self.path == "/api/graph/fields":
            self._send_json(json.dumps(FIELDS).encode())
            return
        if self.path == "/api/graph/data":
            try:
                with open(DATA_FILE, "rb") as fh:
                    body = fh.read()
            except FileNotFoundError:
                body = json.dumps({"nodes": [], "edges": []}).encode()
            self._send_json(body)
            return
        self.send_error(404)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(sys.argv[1])), _Handler).serve_forever()
