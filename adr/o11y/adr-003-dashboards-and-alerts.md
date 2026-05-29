# Dashboards and Alerts

## Context and Problem Statement

[ADR-001](adr-001-cos-integration-architecture.md) commits each charm to providing a `grafana_dashboard` relation and a `metrics-endpoint` relation that can carry alert rules. We need to decide what each charm ships, what the new `charmarr-crowsnest-k8s` charm ships, and what default alerts every charmarr operator gets out of the box.

The split between per-charm and stack-level signals is the central question. Per-charm dashboards answer "is this one app healthy?" Stack-level dashboards answer "is my charmarr deployment healthy as a whole?" Both are needed; both have a natural home.

**Key constraints:**
- Dashboards ship from charms via the standard `grafana_dashboard` relation. No external dashboard repos.
- Alert rules ship through the `prometheus_scrape` relation (Prometheus library auto-collects `src/prometheus_alert_rules/`).
- Default alert rules must be cheap wins — high signal, low noise. Anything heavier requires explicit opt-in.
- Cross-cutting alerts (e.g., "suppress qbit alerts when gluetun is down") cannot live in a single charm. They need a stack-level home.

## Considered Options

### Where Cross-Cutting Dashboards Live
* **Option 1:** Squat on `charmarr-multimeter-k8s` (existing test charm).
* **Option 2:** Ship them from one chosen charm (e.g., `charmarr-storage-k8s`) since it's deployed in every charmarr stack.
* **Option 3:** New dedicated charm (`charmarr-crowsnest-k8s`).
* **Option 4:** External dashboards repo, applied by user against their Grafana.

### Where Cross-Cutting Alert Rules Live
* **Option 1:** Same as dashboards (whichever charm owns dashboards).
* **Option 2:** A separate Sloth-managed flow.
* **Option 3:** Split — cheap-win cross-cutting alerts in crowsnest; SLO-driven alerts in Sloth.

### Default Alert Rule Scope (Per-Charm)
* **Option 1:** Minimal — `up == 0` only.
* **Option 2:** "Cheap wins" — `up == 0`, restart loops, scrape failure, basic resource thresholds.
* **Option 3:** App-specific including queue depth, missing items, failure rates.

## Decision Outcome

**Cross-cutting dashboards: Option 3** — New `charmarr-crowsnest-k8s` charm. Squatting on multimeter conflicts with its test-utility purpose; storage is workload-specific. A dedicated charm is the only home that scales for the work in [adr-004](adr-004-sli-slo-strategy.md).

**Cross-cutting alert rules: Option 3** — Hybrid. Crowsnest ships cheap-win cross-stack alerts (fleet-down thresholds, alert suppression when upstream is down). Sloth ships burn-rate SLO alerts from the SLO specs crowsnest provides. Clean ownership: crowsnest owns the *what*, Sloth owns the *how* for SLOs.

**Default per-charm alerts: Option 2** — Cheap wins by default, app-specific opt-in via charm config. Operators must not be paged by default for arr-app-specific noise (a missing episode is not an oncall event); they must be paged for infra-level failures (charm down, pod crashlooping).

## Implementation Details

### Per-Charm Dashboard Convention

Each charm ships **one** dashboard scoped to itself:

```
charms/<charm>/
├── src/
│   ├── grafana_dashboards/
│   │   └── <charm>.json
```

The dashboard uses the standard Juju topology selectors (`juju_application`, `juju_model`, `juju_unit`) as templated variables. Multi-instance deployments (e.g., `radarr`, `radarr-uhd`, `radarr-anime`) appear as picker options on the same dashboard.

Each per-charm dashboard has:
- Workload health row (up/down, pebble service status, restarts, p99 latency from readiness checks)
- App-specific row (queue depth, library counts, request volumes, exporter-supplied app metrics)
- Resource row (CPU, memory, network from kube-state-metrics joins)

### Per-Charm Alert Rules — The Cheap-Win Baseline

Each charm ships baseline alerts in `src/prometheus_alert_rules/<charm>.rules.yaml`:

```yaml
groups:
  - name: <charm>-baseline
    rules:
      - alert: CharmarrCharmDown
        expr: up{juju_application="<charm>"} == 0
        for: 5m
        labels:
          severity: critical
          stack: charmarr
        annotations:
          summary: "{{ $labels.juju_application }} unit {{ $labels.juju_unit }} is down"

      - alert: CharmarrCharmRestartLoop
        expr: rate(kube_pod_container_status_restarts_total{namespace=~"juju-.*"}[15m]) > 0.1
        for: 10m
        labels:
          severity: warning
          stack: charmarr

      - alert: CharmarrExporterDown
        expr: up{juju_application="<charm>", job=~".*exporter.*"} == 0
        for: 5m
        labels:
          severity: warning
          stack: charmarr
        annotations:
          summary: "Metrics exporter for {{ $labels.juju_application }} is not reachable"

      - alert: CharmarrPebbleServiceDown
        expr: pebble_service_status{state!="active"} == 1
        for: 5m
        labels:
          severity: warning
          stack: charmarr
```

### Per-Charm App-Specific Alerts (Opt-In)

Stuff like "Radarr has more than 50 missing monitored items" goes behind a config option:

```yaml
config:
  options:
    extended-alert-rules:
      type: boolean
      default: false
      description: |
        Enable app-specific alert rules (queue depth, missing items, failure
        thresholds). Off by default — these can be noisy on healthy
        deployments. Recommended only when SLO-style monitoring is wired up.
```

When `extended-alert-rules: true`, the charm additionally ships rules from `src/prometheus_alert_rules/<charm>-extended.rules.yaml`. The provider library is told to load the extended file via `update_alert_rules()` when the config flips.

### Crowsnest Dashboards

`charmarr-crowsnest-k8s` ships cross-cutting dashboards in `src/grafana_dashboards/`:

| Dashboard | What it shows |
|---|---|
| `charmarr-fleet-overview.json` | Every charmarr charm's up/down state, restart counts, recent action invocations, summarized resource heat |
| `charmarr-request-funnel.json` | Seerr→Radarr/Sonarr→qBittorrent/SABnzbd→storage→Plex timing breakdown |
| `charmarr-data-flow.json` | Topology view: relations between charms, signal connectivity |
| `charmarr-vpn-downloads.json` | Gluetun tunnel state correlated with download client throughput and queue depth |
| `charmarr-storage-hotmap.json` | PVC fill %, IO heat per app sub-stack |

These dashboards consume metrics from per-charm exporters *and* from crowsnest's own derived-metrics exporter (see [adr-004](adr-004-sli-slo-strategy.md)).

### Crowsnest Alert Rules

Crowsnest ships stack-level rules in `src/prometheus_alert_rules/charmarr-fleet.rules.yaml`:

| Alert | Logic |
|---|---|
| `CharmarrStackPartialOutage` | `count(up{stack="charmarr"} == 0) / count(up{stack="charmarr"}) > 0.3` for 10m |
| `CharmarrDataFlowBroken` | `charmarr_pipeline_complete == 0` for 15m (some required relation is unwired) |
| `CharmarrVPNDependentAlertNoise` | Suppression marker: when gluetun is down, downstream VPN-dependent app alerts are flagged for routing/silencing |
| `CharmarrRecyclarrDriftHigh` | `max_over_time(charmarr_recyclarr_drift_seconds[1d]) > 86400 * 7` (>7 days since last TRaSH sync) |

The alert suppression logic emits a *signal*, not an Alertmanager rule. Operators wire Alertmanager routes/silences against these signals if they want correlation behavior — crowsnest cannot configure their Alertmanager for them.

### Topology Labels Everywhere

Every dashboard variable uses Juju topology labels (`juju_application`, `juju_model`, `juju_unit`). This makes the dashboards work for multiple charmarr deployments in the same Grafana (e.g., dev + prod stacks).

The Prometheus library injects these labels automatically; we don't have to thread them manually.

## Consequences

### Good

- **Per-charm dashboards work standalone.** Operators who don't deploy crowsnest still get a usable per-app Grafana experience.
- **Cheap-win alerts on by default.** Operators are paged for the failures that matter (charm down) without noise (missing episode).
- **Cross-cutting concerns have a clear home.** Crowsnest dashboards/alerts solve real stack-level problems no individual charm can.
- **Sloth integration is clean.** Crowsnest provides the SLI counters; Sloth handles burn-rate alerting. No double-implementation. See [adr-004](adr-004-sli-slo-strategy.md).
- **Multi-instance support is automatic.** Topology labels mean a user with three Radarr instances sees them on one dashboard without any extra charm work.

### Bad

- **Default cheap-win alerts may still page on healthy upgrades.** A 5-minute charm restart window during refresh can trip `CharmarrCharmDown`. Mitigated by the `for: 5m` window; not perfect.
- **Opt-in extended alerts mean some users get no alerting on workload state.** Acceptable trade-off — false-positive paging is worse than the inverse for opt-out monitoring.

### Neutral

- **Dashboard JSON is hand-authored.** No generation framework. Acceptable for a fixed dashboard set; revisit if we end up with >20 dashboards.

## Related ADRs

- [adr-001-cos-integration-architecture.md](adr-001-cos-integration-architecture.md) — relation contract
- [adr-002-exporter-strategy.md](adr-002-exporter-strategy.md) — what metrics exist to dashboard against
- [adr-004-sli-slo-strategy.md](adr-004-sli-slo-strategy.md) — Sloth integration, SLI/SLO ownership
