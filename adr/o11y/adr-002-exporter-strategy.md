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
* **Option 2:** Sidecar container inside the same pod, using the upstream exporter's published OCI image directly as a charm `resource`. Pebble (Juju-injected per container) manages its service. Same pattern Recyclarr already uses inside the arr charms today.
* **Option 3:** Extra Pebble service inside the existing workload container, with the exporter binary delivered via charm-parts + `container.push()`.

### How the Exporter Binary is Distributed
* **Option 1:** Upstream OCI image as a sidecar container resource — `charmcraft.yaml` declares the exporter image alongside the workload image; no repackaging, Renovate tracks the tag. Only viable when the upstream publishes an image.
* **Option 2:** Custom OCI image — fork-and-layer the exporter binary on top of the upstream workload image; charmcraft.yaml resources point at our published variant. Renovate tracks both upstream and exporter tags.
* **Option 3:** Charm-parts + Pebble push — declare the exporter binary as a `parts:` artifact (downloaded at pack time, embedded in the `.charm` file), and the charm pushes it into a workload-side container via `container.push()`. Only path when no upstream OCI image exists and the exporter is a static binary.
* **Option 4:** Runtime download — the charm `curl`s the exporter binary on first reconcile from an external URL.

### Per-Charm vs Centralized Exporter for Arr Apps
* **Option 1:** Per-charm exporter — each arr charm (radarr, sonarr, prowlarr) runs its own scraparr instance scoped to itself.
* **Option 2:** Centralized exporter — single scraparr instance in the `charmarr-crowsnest-k8s` charm polls all related arr instances via relation data.

### Arr-App Exporter Choice
* **Option 1:** `onedr0p/exportarr` — battle-tested, ~1.3k stars, **maintenance mode**, supports radarr/sonarr/prowlarr/sabnzbd in one binary.
* **Option 2:** `thecfu/scraparr` — newer, actively developed, covers radarr/sonarr/prowlarr/jellyseerr, similar single-binary deployment.
* **Option 3:** App-specific exporters — one per arr app, more moving parts.

### qBittorrent Exporter Choice
* **Option 1:** `esanchezm/prometheus-qbittorrent-exporter` (Python, ~700 stars, established).
* **Option 2:** `martabal/qbittorrent-exporter` (Go, modern, tag/category labels).

### Plex Exporter Choice
* **Option 1:** `axsuul/plex-media-server-exporter` (Ruby, most complete metric set, actively maintained with proper semver-tagged multi-arch releases).
* **Option 2:** `jsclayton/prometheus-plex-exporter` (Go, single binary, simpler ops but no tagged multi-arch releases - only `:latest` is multi-arch; Renovate can't track digest moves without a regex manager extension).

### Seerr / Overseerr Exporter Choice
* **Option 1:** `WillFantom/overseerr-exporter` (Go, ~30 stars, last commit October 2023 — 1.5+ years stale at time of evaluation).
* **Option 2:** No per-charm exporter — rely on kube-state-metrics for pod liveness only.

### Gluetun Exporter Choice
* **Option 1:** Custom Python shim distributed via charm-parts (~150 LoC), polling Gluetun's control API and emitting Prometheus metrics (see [adr-005](adr-005-gluetun-metrics-shim.md) — original plan).
* **Option 2:** `thecfu/gluetun-exporter:0.1.1-standalone` — third-party Go exporter (same author as scraparr), polls Gluetun's HTTP control API, exposed via Pebble service in the workload container.
* **Option 3:** `thecfu/gluetun-exporter:0.1.1-bundled` — same exporter, but rebuilt on top of the Gluetun image with `CAP_NET_ADMIN` to read netlink throughput counters.

## Decision Outcome

**Where the exporter runs: Option 2** — Sidecar container in the same pod as the workload. Mirrors the Recyclarr container that arr charms already ship. Each container has its own Pebble (Juju-injected), so the charm reconciler owns the exporter's service lifecycle the same way it owns the workload's. Workload image stays the upstream pristine variant.

**How the binary is distributed: Option 1 (primary), Option 3 (fallback)** — Use the upstream exporter's published OCI image directly as a charm `resource` whenever the project publishes one. All current picks (scraparr, qbittorrent-exporter, plex-exporter, overseerr-exporter, sabnzbd_exporter) ship OCI images, so this is the uniform path. Charm-parts + Pebble push remains as the fallback for the Gluetun shim (no upstream image — we own the code; see [adr-005](adr-005-gluetun-metrics-shim.md)). Custom OCI images (Option 2) are rejected — 11+ charm-specific image build pipelines is real maintenance burden when upstream already publishes images. Runtime download (Option 4) is rejected for breaking air-gapped deploys and decoupling exporter version from charm revision.

**Per-charm vs centralized arr exporter: Option 1** — Per-charm. Centralizing scraparr in crowsnest is elegant on paper but breaks standalone charm composability: a user deploying just `radarr-k8s` would have no metrics for it. The Canonical-ecosystem expectation is that a charm with a `metrics-endpoint` relation produces useful metrics on its own. ~30-50MB resident memory per scraparr instance × typical 3 arr charms is negligible cost compared to the architectural cleanness. Crowsnest's role becomes purely derived/cross-cutting metrics (PromQL queries over per-charm exporter output), not scrape orchestration.

**Arr-app exporter: Option 2** — `thecfu/scraparr` as the default. Active development is the key requirement; exportarr's maintenance mode is a future liability. Fallback to exportarr if scraparr can't cover a specific arr in the rollout.

**qBittorrent exporter: Option 2** — `martabal/qbittorrent-exporter` (Go). Modern, label semantics match the multi-instance pattern of charmarr's qbit deployments, single binary.

**Plex exporter: Option 1** — `axsuul/plex-media-server-exporter` (Ruby). Initial pick was jsclayton's Go binary for "simpler ops", but the project ships no semver-tagged multi-arch images (`:latest` is the only multi-arch ref), so version pinning loses Renovate auto-update support without extending the Renovate regex manager. axsuul ships proper tagged multi-arch releases (`2.1.0` and forward) and surfaces the metrics that actually matter operationally: live `plex_sessions_count{state, user, ...}`, `plex_video_transcode_sessions_count` for transcode pressure, `plex_media_count{type}` for library scale. jsclayton's metric set was ~6 metrics with limited operational signal (host_cpu/mem, library_storage_total, plays_total) — too thin for real alerts. Ruby image is ~150 MB vs Go's ~10 MB; acceptable trade for the richer signal.

**Seerr / Overseerr exporter: Option 2** — no per-charm exporter. WillFantom's exporter is the only Prometheus-native option and is stale (no commits for 18+ months), with sparse metrics (just two metric families: `overseerr_requests_count`, `overseerr_user_requests`). The signals it provides are also derivable from Seerr's own admin UI — no operational gap to fill. Liveness is covered by kube-state-metrics + the crowsnest charm's topology-completeness signal once it exists. Operators who want request analytics should deploy Tautulli alongside.

**Gluetun exporter: Option 2** — `thecfu/gluetun-exporter:0.1.1-standalone` sidecar. Original plan ([adr-005](adr-005-gluetun-metrics-shim.md)) was a custom Python shim distributed via charm-parts, but that assumed Python was available in Gluetun's container; Gluetun is built on alpine + Go binary with no Python. A pre-existing Go exporter by the scraparr author (already trusted in our fleet) covers the essentials — `gluetun_vpn_status`, `gluetun_vpn_infos{ip, country, city}`, `gluetun_forwarded_ports*` — at zero maintenance cost to charmarr. Standalone mode runs as a sidecar with localhost access to Gluetun's control API; bundled mode requires `CAP_NET_ADMIN` and rebuilds the workload image — overkill given cAdvisor already provides container_network_* counters from kube-state-metrics. ADR-005 is superseded.

## Implementation Details

### Per-App Exporter Inventory

| Charm | Exporter | Image | Container Name | Port |
|---|---|---|---|---|
| `radarr-k8s` | scraparr | `ghcr.io/thecfu/scraparr` | `scraparr` | 7100 |
| `sonarr-k8s` | scraparr | same | `scraparr` | 7100 |
| `prowlarr-k8s` | scraparr | same | `scraparr` | 7100 |
| `qbittorrent-k8s` | martabal/qbittorrent-exporter | `ghcr.io/martabal/qbittorrent-exporter` | `qbittorrent-exporter` | 8090 |
| `sabnzbd-k8s` | msroest/sabnzbd_exporter | `docker.io/msroest/sabnzbd_exporter` | `sabnzbd-exporter` | 9387 |
| `plex-k8s` | axsuul/plex-media-server-exporter | `ghcr.io/axsuul/plex-media-server-exporter` | `plex-exporter` | 9594 |
| `seerr-k8s` | **None** — no acceptable exporter; rely on kube-state-metrics + crowsnest topology checks for liveness | n/a | n/a | n/a |
| `overseerr-k8s` | **None** — same as seerr | n/a | n/a | n/a |
| `flaresolverr-k8s` | **Native** (`PROMETHEUS_ENABLED=true`) | n/a (workload image) | n/a | 8192 (default workload port) |
| `gluetun-k8s` | thecfu/gluetun-exporter (standalone) | `ghcr.io/thecfu/gluetun-exporter:0.1.1-standalone` | `gluetun-exporter` | 8001 |
| `charmarr-storage-k8s` | None — PVC metrics from kube-state-metrics | n/a | n/a | n/a |
| `charmarr-multimeter-k8s` | None — test utility | n/a | n/a | n/a |
| `charmarr-crowsnest-k8s` | Custom Python — derived/stack metrics | charmarr-built (see [adr-003](adr-003-dashboards-and-alerts.md)) | `metrics` Pebble service | 9090 |

### Distribution: Sidecar Container with Upstream OCI

Each exporter declares an extra container in `charmcraft.yaml`, sourced from the upstream's published image. Same shape as Recyclarr in the arr charms today.

```yaml
containers:
  radarr:
    resource: radarr-image
    mounts:
      - storage: config
        location: /config
  recyclarr:
    resource: recyclarr-image
  scraparr:
    resource: scraparr-image

resources:
  radarr-image:
    type: oci-image
    description: OCI image for Radarr (LinuxServer)
    upstream-source: lscr.io/linuxserver/radarr:6.1.1.10360-ls299
  recyclarr-image:
    type: oci-image
    description: OCI image for Recyclarr
    upstream-source: ghcr.io/recyclarr/recyclarr:7.5.2
  scraparr-image:
    type: oci-image
    description: OCI image for scraparr (Prometheus exporter for *arr apps)
    upstream-source: ghcr.io/thecfu/scraparr:<pin>
```

Renovate tracks `upstream-source:` tags like the workload image — uniform PR shape across all images.

**Why not custom OCI images:** maintaining 11+ charmarr-specific exporter images is real overhead (build pipelines, registry hosting, fork drift) when upstream already publishes images.

**Why not charm-parts for every exporter:** while elegant for embedding a static Go binary, it forces us to push binaries into containers that may not have the right runtime (e.g. scraparr is a Python package, not a Go binary — LinuxServer's Alpine image has no Python).

**Why not runtime download:** breaks air-gapped deploys; decouples exporter version from charm revision.

**When charm-parts still applies:** no current use case. The original Gluetun shim plan (custom Python via charm-parts) is superseded by the thecfu/gluetun-exporter sidecar — see [adr-005](adr-005-gluetun-metrics-shim.md) for the revised decision. The charm-parts mechanism remains available as a fallback for any future charm that needs an exporter and has no acceptable upstream image, but the fleet currently has no instance of that pattern.

### Pebble Layer Pattern

Each container gets its own Juju-injected Pebble. The charm reconciler adds a layer to each container.

Workload container (unchanged from today):

```python
def _build_workload_layer(self) -> ops.pebble.LayerDict:
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
        },
        "checks": {f"{CONTAINER_NAME}-ready": {...}},
    }
```

Exporter sidecar container (new — one per charm):

```python
def _build_exporter_layer(self) -> ops.pebble.LayerDict:
    return {
        "services": {
            "exporter": {
                "override": "replace",
                "command": f"{EXPORTER_ENTRYPOINT} --listen :{METRICS_PORT}",
                "startup": "enabled",
                "environment": {
                    "WORKLOAD_URL": f"http://{POD_LOCALHOST}:{WEBUI_PORT}",
                    "WORKLOAD_API_KEY": "<from juju secret>",
                },
            },
        },
        "checks": {
            "metrics-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": f"http://localhost:{METRICS_PORT}/metrics"},
            },
        },
    }
```

The exporter reaches the workload over `localhost` (same pod, same network namespace). The charm passes the workload API key from the existing Juju secret into the sidecar via environment variable.

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
- **No fork/maintain of upstream images.** Sidecar OCI resources point straight at upstream registries. Renovate handles version tracking the same way it tracks workload image tags.
- **Runtime mismatches are a non-problem.** Python-based exporters (scraparr, sabnzbd_exporter) ship their own Python runtime in their image; Go exporters ship single static binaries in their image. The workload container stays untouched.
- **Charm standalone composability preserved.** Each charm produces useful metrics on its own — no hidden dependency on crowsnest or any other charmarr charm.
- **Charm owns the exporter lifecycle.** Each sidecar gets its own Juju-injected Pebble; restarts, secret-key rotation, config drift are all reconciled by the existing charm code paths.
- **Active upstream for every choice.** scraparr/martabal/axsuul/thecfu are all currently maintained with proper tagged multi-arch releases. Inactive upstreams (jsclayton for plex, WillFantom for overseerr) were rejected after live evaluation — see the per-app decision rationale for plex and seerr.
- **Exporter health is observable.** Pebble checks + status surface failures the same way the workload does. Sidecar crashes don't take down the workload container, and vice versa.

### Bad

- **One extra container per charm in the pod.** Most charms go from 1 container (workload) to 2 (workload + exporter); arr charms go from 2 (workload + recyclarr) to 3. ~50-100MB extra memory per sidecar. Acceptable for the operational simplicity.
- **Exporter API key handling per app.** Each exporter needs the workload API key as env. Adds wiring but it's mechanical.
- **scraparr's multi-instance feature is unused.** Each per-charm instance polls only its local arr. Acceptable trade-off for standalone composability.
- **scraparr is young.** We're betting on an active but unproven project. Mitigation: keep exportarr as a documented fallback per arr if scraparr regresses.
- **Inter-container communication via localhost.** Sidecar reaches workload over `localhost`. Standard K8s pod networking — no surprises — but worth noting as an implicit contract.

### Neutral

- **No user dashboard for Plex** (top users, watch times, etc.) from this exporter set. Acknowledged out-of-scope; Tautulli integration is a later effort.

## Related ADRs

- [adr-001-cos-integration-architecture.md](adr-001-cos-integration-architecture.md) — overall architecture
- [adr-003-dashboards-and-alerts.md](adr-003-dashboards-and-alerts.md) — what metrics drive dashboards/alerts
- [adr-005-gluetun-metrics-shim.md](adr-005-gluetun-metrics-shim.md) — custom Gluetun shim (the one exception)
- [apps/adr-014-release-flow.md](../apps/adr-014-release-flow.md) — OCI image release/Renovate pattern
