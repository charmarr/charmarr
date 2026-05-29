# Gluetun Metrics Shim

## Context and Problem Statement

[ADR-002](adr-002-exporter-strategy.md) commits every charmarr charm to exposing Prometheus metrics via an exporter. Gluetun is the one charm where no acceptable third-party exporter exists. Upstream Gluetun has [an open feature request for native Prometheus metrics](https://github.com/qdm12/gluetun/issues/279) but no implementation. There is no mature community exporter.

Gluetun does expose an HTTP control API on port 8000 with endpoints like `/v1/vpn/status`, `/v1/publicip/ip`, and `/v1/openvpn/portforwarded`. The data we need is there — we just need to translate JSON to Prometheus format.

**Key constraints:**
- The shim must follow the same Pebble service pattern as every other charm's exporter.
- It must be maintained by charmarr (no upstream to depend on) but should be tiny enough that maintenance burden is negligible.
- It must not depend on Gluetun internals beyond the documented control API.
- Output must support the charmarr-crowsnest charm's SLI metric `charmarr_vpn_tunnel_up` for the VPN availability SLO.

## Considered Options

### Implementation Language
* **Option 1:** Go — single static binary, follows the other Go-based exporters' pattern.
* **Option 2:** Python — easier to maintain inline with the charm, leverages existing charm-side dependencies.
* **Option 3:** Shell + Prometheus textfile collector — minimal, no code base required.

### Where the Shim Lives
* **Option 1:** Standalone repo (e.g., `charmarr/gluetun-exporter`) with its own release flow.
* **Option 2:** Inside the `gluetun-k8s` charm source tree (e.g., `charms/gluetun-k8s/exporter/`), travelling with the charm revision.
* **Option 3:** Inside `charmarr-lib` as a reusable component.

### Distribution
* **Option 1:** Custom OCI image — bake the script into a charm-local OCI variant of the upstream Gluetun image.
* **Option 2:** Charm source + Pebble push — embed the script in the charm source tree; push it into the workload container on reconcile via `container.push()`. Same pattern as [adr-002](adr-002-exporter-strategy.md).
* **Option 3:** Run as a sidecar container.
* **Option 4:** Run on the host of the charm container, scrape via mTLS.

## Decision Outcome

**Language: Option 2** — Python. The exporter is ~150 LoC. Python's standard library `http.server` plus `urllib` is sufficient. Stays in the charmarr ecosystem (everything else is Python), no Go toolchain in the build pipeline.

**Location: Option 2** — Inside `gluetun-k8s` charm source. Same pattern as Recyclarr in the arr charms. The shim is tightly coupled to Gluetun specifically; sharing via charmarr-lib would only matter if a second consumer existed.

**Distribution: Option 2** — Charm source + Pebble push. Mirrors [adr-002](adr-002-exporter-strategy.md)'s decision for the fleet. The script lives in `exporter/gluetun_exporter.py` in the charm source; the charm pushes it into the workload container on reconcile. No custom OCI image — Gluetun's upstream image stays pristine.

## Implementation Details

### Source Layout

```
charms/gluetun-k8s/
├── exporter/                          ← NEW
│   ├── README.md
│   ├── gluetun_exporter.py            (the shim itself)
│   └── tests/
│       └── test_exporter.py
├── src/
│   ├── charm.py
│   ├── _gluetun/
│   ├── grafana_dashboards/
│   │   └── gluetun.json
│   └── prometheus_alert_rules/
│       └── gluetun.rules.yaml
└── ...
```

### Metrics Exposed

```
# HELP gluetun_vpn_up Whether the VPN tunnel is currently up (1) or down (0)
# TYPE gluetun_vpn_up gauge
gluetun_vpn_up{provider="protonvpn"} 1

# HELP gluetun_public_ip_info Public IP visible from outside the tunnel
# TYPE gluetun_public_ip_info gauge
gluetun_public_ip_info{ip="185.230.124.42",country="NL",city="Amsterdam",organization="ProtonVPN"} 1

# HELP gluetun_port_forwarded Forwarded port number from the VPN provider
# TYPE gluetun_port_forwarded gauge
gluetun_port_forwarded 51820

# HELP gluetun_connect_seconds Seconds the current VPN connection has been up
# TYPE gluetun_connect_seconds counter
gluetun_connect_seconds 14582

# HELP gluetun_reconnect_total Total number of VPN reconnections observed
# TYPE gluetun_reconnect_total counter
gluetun_reconnect_total 7

# HELP gluetun_control_api_reachable Whether the Gluetun control API is reachable
# TYPE gluetun_control_api_reachable gauge
gluetun_control_api_reachable 1
```

The `_info` metric pattern with labels follows Prometheus conventions for "current state" attributes that don't aggregate (IP, country, etc.).

### Polling Pattern

The shim is a small HTTP server that, on each scrape, queries Gluetun's control API and renders the result as text:

```python
class GluetunMetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return
        metrics = self._collect()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(metrics.encode())

    def _collect(self) -> str:
        # Query Gluetun control API endpoints, build metrics text
        ...
```

Caches between scrapes are kept short (30s default) to avoid hammering the Gluetun control API.

### Pebble Layer Integration

Gluetun's charm gets the standard exporter service alongside the workload:

```python
def _build_pebble_layer(self) -> ops.pebble.LayerDict:
    return {
        "services": {
            "gluetun": {
                "override": "replace",
                "command": "/gluetun-entrypoint",
                # ... existing config ...
            },
            "metrics": {
                "override": "replace",
                "command": "python3 /opt/charmarr/gluetun_exporter.py",
                "startup": "enabled",
                "after": ["gluetun"],
                "requires": ["gluetun"],
                "environment": {
                    "GLUETUN_API_URL": "http://localhost:8000",
                    "METRICS_PORT": "9876",
                    "CACHE_SECONDS": "30",
                },
            },
        },
        "checks": {
            "gluetun-ready": {...},
            "metrics-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": "http://localhost:9876/metrics"},
            },
        },
    }
```

### Binary Distribution

The shim script is embedded in the charm source at `exporter/gluetun_exporter.py`. The charm pushes it into the workload container on reconcile:

```python
def _ensure_exporter_script(self) -> None:
    src = self.charm_dir / "exporter" / "gluetun_exporter.py"
    self._container.push(
        "/opt/charmarr/gluetun_exporter.py",
        src.read_bytes(),
        permissions=0o755,
        make_dirs=True,
    )
```

The Pebble layer then runs `python3 /opt/charmarr/gluetun_exporter.py`. Python is already in Gluetun's upstream image, so no extra dependency installation is needed.

Gluetun's upstream OCI image stays pristine (`qmcgaw/gluetun:<tag>`) — no charm-local image fork. Renovate tracks only the upstream Gluetun tag; the shim version is part of the charm source and travels with the charm revision.

### Alert Rules

Gluetun's charm-shipped baseline alerts add:

```yaml
- alert: CharmarrVPNTunnelDown
  expr: gluetun_vpn_up == 0
  for: 2m
  labels:
    severity: critical
    stack: charmarr
  annotations:
    summary: "Gluetun VPN tunnel is down"
    description: |
      Downloads via qBittorrent/SABnzbd/Prowlarr will not flow until the
      tunnel reconnects. If this persists, check Gluetun container logs
      and VPN provider credentials.

- alert: CharmarrVPNReconnectStorm
  expr: rate(gluetun_reconnect_total[15m]) > 0.1
  for: 10m
  labels:
    severity: warning
    stack: charmarr

- alert: CharmarrVPNControlAPIUnreachable
  expr: gluetun_control_api_reachable == 0
  for: 5m
  labels:
    severity: warning
    stack: charmarr
```

### Dashboard

A single Gluetun panel in `src/grafana_dashboards/gluetun.json`:
- Tunnel up/down timeline
- Connection uptime
- Reconnect count over time
- Public IP & location (info table)
- Forwarded port status
- Crowsnest's `charmarr-vpn-downloads.json` joins these with downstream client throughput.

### Test Strategy

- Unit tests cover the JSON-to-Prometheus translation.
- Integration tests deploy the charm with a stub Gluetun container and assert the exporter responds with expected metrics.
- A nightly test verifies the public IP changes when forced to reconnect (basic end-to-end VPN validation).

## Consequences

### Good

- **One small thing we own.** ~150 LoC of Python is negligible maintenance burden.
- **Uniform pattern with other exporters.** No special case in the charm or in COS wiring.
- **Feeds the crowsnest SLO.** `vpn-tunnel-availability` SLO references `gluetun_vpn_up` directly.
- **Independent of Gluetun internals.** Only uses the public control API.
- **Future migration is clean.** If upstream Gluetun adds native metrics, we delete the shim and update the charm to set `PROMETHEUS_ENABLED` (or whatever flag they choose).

### Bad

- **Polling overhead.** Each scrape hits Gluetun's control API. Capped by the 30s cache; impact is negligible.
- **One more thing to maintain.** Yes. ~150 LoC. Acceptable.

### Neutral

- **Shim version is coupled to charm revision.** Updating the shim requires a charm revision. Acceptable — the shim is tiny and rarely changes.

## Related ADRs

- [adr-002-exporter-strategy.md](adr-002-exporter-strategy.md) — the pattern we're conforming to
- [adr-003-dashboards-and-alerts.md](adr-003-dashboards-and-alerts.md) — where Gluetun's signals get correlated
- [adr-004-sli-slo-strategy.md](adr-004-sli-slo-strategy.md) — `vpn-tunnel-availability` SLO consumes `gluetun_vpn_up`
- [apps/adr-006-gluetun-k8s.md](../apps/adr-006-gluetun-k8s.md) — Gluetun charm baseline design
- [interfaces/adr-007-vpn-gateway.md](../interfaces/adr-007-vpn-gateway.md) — VPN gateway relation, downstream consumers
