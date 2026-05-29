# Per-App Exporter Strategy

## Context and Problem Statement

[ADR-001](adr-001-cos-integration-architecture.md) commits each charm to exposing a Prometheus `/metrics` endpoint. None of the workload apps (Radarr, Sonarr, Plex, qBittorrent, etc.) emit Prometheus-native metrics with the exception of FlareSolverr. We need to pick an exporter strategy per app, decide where the exporter runs, and standardize the integration pattern.

**Key constraints:**
- Exporters must be active, maintained projects. We do not want to ship a charm dependent on a stagnant binary.
- Exporters should add minimal overhead — no separate pods if avoidable.
- The integration pattern must be uniform across charms so the rollout is mechanical.
- One arr exporter project (`exportarr`) is in maintenance mode; we need a forward-looking replacement.

## Considered Options

### Where the Exporter Runs
* **Option 1:** Sidecar pod alongside the workload pod, integrated via service mesh.
* **Option 2:** Sidecar container inside the same pod (extra K8s container).
* **Option 3:** Extra Pebble service inside the existing workload container.

### Arr-App Exporter Choice
* **Option 1:** `onedr0p/exportarr` — battle-tested, ~1.3k stars, **maintenance mode**, supports radarr/sonarr/prowlarr/sabnzbd in one binary.
* **Option 2:** `thecfu/scraparr` — newer, actively developed, covers radarr/sonarr/prowlarr/jellyseerr, similar single-binary deployment.
* **Option 3:** App-specific exporters — one per arr app, more moving parts.

### qBittorrent Exporter Choice
* **Option 1:** `esanchezm/prometheus-qbittorrent-exporter` (Python, ~700 stars, established).
* **Option 2:** `martabal/qbittorrent-exporter` (Go, modern, tag/category labels).

### Plex Exporter Choice
* **Option 1:** `axsuul/plex-media-server-exporter` (Ruby, most complete metric set).
* **Option 2:** `jsclayton/prometheus-plex-exporter` (Go, single binary, simpler ops).

## Decision Outcome

**Where the exporter runs: Option 3** — Pebble service in the workload container. Same pattern as Recyclarr in the arr charms today. Zero extra containers, charm fully owns the lifecycle, exporter restarts independently if it crashes.

**Arr-app exporter: Option 2** — `thecfu/scraparr` as the default. Active development is the key requirement; exportarr's maintenance mode is a future liability. Fallback to exportarr if scraparr can't cover a specific arr in the rollout.

**qBittorrent exporter: Option 2** — `martabal/qbittorrent-exporter` (Go). Modern, label semantics match the multi-instance pattern of charmarr's qbit deployments, single binary.

**Plex exporter: Option 2** — `jsclayton/prometheus-plex-exporter` (Go). Single binary, simpler operationally. The richer "user/title" data from `axsuul` is best served by Tautulli (out of scope for this ADR; user-facing analytics dashboard is later work).

## Implementation Details

### Per-App Exporter Inventory

| Charm | Exporter | Source | Pebble Service | Port |
|---|---|---|---|---|
| `radarr-k8s` | scraparr | github.com/thecfu/scraparr | `metrics` | 7878 (configurable) |
| `sonarr-k8s` | scraparr | same | `metrics` | 7878 |
| `prowlarr-k8s` | scraparr | same | `metrics` | 7878 |
| `qbittorrent-k8s` | martabal/qbittorrent-exporter | github.com/martabal/qbittorrent-exporter | `metrics` | 8090 |
| `sabnzbd-k8s` | msroest/sabnzbd_exporter | github.com/msroest/sabnzbd_exporter | `metrics` | 9387 |
| `plex-k8s` | jsclayton/prometheus-plex-exporter | github.com/jsclayton/prometheus-plex-exporter | `metrics` | 9594 |
| `seerr-k8s` | WillFantom/overseerr-exporter (Seerr API compat verified) | github.com/WillFantom/overseerr-exporter | `metrics` | 9850 |
| `overseerr-k8s` | Same as seerr | same | `metrics` | 9850 |
| `flaresolverr-k8s` | **Native** (`PROMETHEUS_ENABLED=true`) | n/a | n/a | 8192 (default workload port) |
| `gluetun-k8s` | Custom Python shim | charmarr (see [adr-005](adr-005-gluetun-metrics-shim.md)) | `metrics` | 9876 |
| `charmarr-storage-k8s` | None — PVC metrics from kube-state-metrics | n/a | n/a | n/a |
| `charmarr-multimeter-k8s` | None — test utility | n/a | n/a | n/a |
| `charmarr-crowsnest-k8s` | Custom Python — derived/stack metrics | charmarr (see [adr-003](adr-003-dashboards-and-alerts.md)) | `metrics` | 9090 |

### OCI Image Strategy

Exporters get baked into a charm-local OCI image layered on top of the upstream workload image. Per charm:

```
charms/radarr-k8s/
├── oci/                              ← NEW
│   ├── Dockerfile                    (FROM lscr.io/linuxserver/radarr + scraparr binary)
│   └── README.md
```

Renovate watches the upstream workload image *and* the exporter release tag. Two PRs per dependency update — manageable.

Alternative considered and rejected: download exporter binary at first-start via Pebble. Adds runtime network dependency, complicates air-gapped deployments, breaks the "image is the contract" invariant.

### Pebble Layer Pattern

Standardized across charms. Workload definitions in the `_<charmname>` private module add an `exporter` service alongside the main `workload` service:

```python
def _build_pebble_layer(self) -> ops.pebble.LayerDict:
    return {
        "services": {
            "workload": {
                "override": "replace",
                "command": "/path/to/main/binary",
                "startup": "enabled",
                "user-id": DEFAULT_PUID,
                "group-id": DEFAULT_PGID,
                "environment": {...},
            },
            "exporter": {
                "override": "replace",
                "command": f"/usr/local/bin/{EXPORTER_BINARY} --listen :{METRICS_PORT}",
                "startup": "enabled",
                "after": ["workload"],
                "requires": ["workload"],
                "environment": {
                    "WORKLOAD_URL": f"http://localhost:{WEBUI_PORT}",
                    "WORKLOAD_API_KEY": "<from juju secret>",
                },
            },
        },
        "checks": {
            f"{CONTAINER_NAME}-ready": {...},
            f"{CONTAINER_NAME}-metrics-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": f"http://localhost:{METRICS_PORT}/metrics"},
            },
        },
    }
```

The exporter typically needs the workload API key, which the charm already manages as a Juju secret. The charm passes it into the exporter via environment variable.

### MetricsEndpointProvider Wiring

One line per charm:

```python
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider

self._metrics = MetricsEndpointProvider(
    self,
    jobs=[{"static_configs": [{"targets": [f"*:{METRICS_PORT}"]}]}],
)
```

The library handles relation events and forwards the target list to whatever Prometheus is related on the other side.

### Alert Rules Companion

Each charm ships baseline alert rules in `src/prometheus_alert_rules/<charm>.rules.yaml`. The library auto-ships them through the same `metrics-endpoint` relation. See [adr-003](adr-003-dashboards-and-alerts.md) for the default ruleset.

### Health Check Integration

Each charm adds a Pebble `ready` check for its exporter's `/metrics` endpoint. If the exporter dies, the readiness probe surfaces it; the charm's `_collect_workload_status` reports `WaitingStatus("Waiting for exporter")` and an alert fires.

## Consequences

### Good

- **One pattern, eleven charms.** Rolling out per-app exporters is mechanical after the first reference implementation (radarr).
- **No extra containers, no extra pods.** Lower resource footprint, fewer K8s objects to debug.
- **Charm owns the exporter lifecycle.** Restarts, secret-key rotation, config drift are all reconciled by the existing charm code paths.
- **Active upstream for every choice.** scraparr/martabal/jsclayton are all currently maintained, avoiding the exportarr-style aging problem.
- **Exporter health is observable.** Pebble checks + status surface failures the same way the workload does.

### Bad

- **OCI image maintenance fan-out.** Each charm's OCI image needs renovate'ing for both the workload and the exporter. ~11 images to maintain instead of ~11 workload images + 1 exporter image.
- **Exporter API key handling per app.** Each exporter needs the workload API key as env. Adds wiring but it's mechanical.
- **scraparr is young.** We're betting on an active but unproven project. Mitigation: keep exportarr as a documented fallback per arr if scraparr regresses.

### Neutral

- **No user dashboard for Plex** (top users, watch times, etc.) from this exporter set. Acknowledged out-of-scope; Tautulli integration is a later effort.

## Related ADRs

- [adr-001-cos-integration-architecture.md](adr-001-cos-integration-architecture.md) — overall architecture
- [adr-003-dashboards-and-alerts.md](adr-003-dashboards-and-alerts.md) — what metrics drive dashboards/alerts
- [adr-005-gluetun-metrics-shim.md](adr-005-gluetun-metrics-shim.md) — custom Gluetun shim (the one exception)
- [apps/adr-014-release-flow.md](../apps/adr-014-release-flow.md) — OCI image release/Renovate pattern
