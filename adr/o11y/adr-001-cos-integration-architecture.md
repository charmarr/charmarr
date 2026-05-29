# COS Integration Architecture

## Context and Problem Statement

Charmarr ships a stack of media charms with no observability today. Operators have no visibility into charm health, workload metrics, logs, traces, or stack-wide signals beyond what `juju status` shows. We want clean integration with the Canonical Observability Stack (COS) so users can deploy any COS flavor of their choice (`cos-lite`, `cos-dev`, `cos`) and have charmarr light up with metrics, logs, traces, and dashboards.

**Key constraints:**
- Charmarr does not own COS lifecycle. The user deploys and operates their own COS — same pattern as Istio today.
- Every charmarr charm must work standalone (no observability) and with any COS flavor (graceful no-op when a pillar isn't available).
- Cross-model relations are the integration surface. Charmarr lives in one model, COS in another.
- Three pillars matter: metrics, logs, traces. Plus dashboards as the delivery channel.

## Considered Options

### Deployment Topology
* **Option 1:** Bundle deploys COS alongside charmarr (`enable_observability = true` flag).
* **Option 2:** Charmarr ships relations only; user deploys their own COS and integrates cross-model.

### Per-Charm vs Aggregate Producer
* **Option 1:** Each charm exposes its own metrics/logs/traces/dashboards independently.
* **Option 2:** Single aggregate observability charm sits in front of all charmarr charms and proxies signals upstream.
* **Option 3:** Per-charm signals + a dedicated stack-level charm for cross-cutting concerns.

### Dev/Reference COS Flavor
* **Option 1:** `cos-lite` (monolithic, lightweight, but no Tempo for tracing).
* **Option 2:** `cos` (full distributed, all pillars, heavy footprint).
* **Option 3:** `cos-dev` in monolithic mode (lightweight footprint, all three pillars including Tempo).

## Decision Outcome

**Deployment Topology: Option 2** — User deploys COS, charmarr provides integrations. Matches existing Istio pattern. No `enable_observability` flag in our terraform bundle. Charmarr stays pure media-stack code with no opinions on the observability layer it talks to.

**Per-Charm vs Aggregate: Option 3** — Per-charm relations for the standard pillars, plus a new `charmarr-crowsnest-k8s` charm for stack-level signals (cross-app derived metrics, fleet dashboards, alert correlation, SLO specs). Pure aggregate (Option 2) loses per-charm granularity in Grafana; pure per-charm (Option 1) has no home for cross-cutting work.

**Dev/Reference Flavor: Option 3** — `cos-dev` monolithic mode. Smallest footprint that includes all three pillars. Our docs do not recommend a flavor (that's COS's product responsibility); our development, testing, and CI target `cos-dev` because it exercises every relation we ship.

## Implementation Details

### Per-Charm Relations

Every charmarr charm (existing 11 + the new crowsnest charm) declares:

```yaml
provides:
  metrics-endpoint:
    interface: prometheus_scrape
    optional: true
    description: Prometheus scrapes this charm's /metrics endpoint
  grafana-dashboard:
    interface: grafana_dashboard
    optional: true
    description: Charm-shipped Grafana dashboards
requires:
  logging:
    interface: loki_push_api
    optional: true
    description: Workload + charm logs pushed to Loki
  charm-tracing:
    interface: tracing
    optional: true
    limit: 1
    description: Charm hook execution traces to Tempo
```

All four are `optional: true`. Operators wire as many or as few as their COS deployment supports.

### Charm Libraries Used

Standard Canonical libraries, fetched via `charm-libs:` (same pattern as Istio):

| Pillar | Library | Pattern |
|---|---|---|
| Metrics | `charms.prometheus_k8s.v0.prometheus_scrape.MetricsEndpointProvider` | Auto-picks up `src/prometheus_alert_rules/` |
| Dashboards | `charms.grafana_k8s.v0.grafana_dashboard.GrafanaDashboardProvider` | Auto-picks up `src/grafana_dashboards/` |
| Logs | `charms.loki_k8s.v1.loki_push_api.LokiPushApiConsumer` | Forwards Pebble service logs |
| Traces | `charms.tempo_coordinator_k8s.v0.tracing.TracingEndpointRequirer` | Used by `ops[tracing]` |

### Charm-Side Tracing

`ops[tracing]` integration is one-line: declare `ops>=2.17` with the `tracing` extra in each charm's `pyproject.toml`. The framework auto-emits one span per hook execution. No charm-code changes beyond the relation declaration.

### Metrics Source per Charm

Each charm runs an additional Pebble service in its workload container that exposes a Prometheus `/metrics` endpoint. See [adr-002](adr-002-exporter-strategy.md) for per-app exporter choices.

### Workload Log Forwarding

The `LokiPushApiConsumer` pattern tails Pebble service logs (stdout/stderr captured by Pebble) and forwards them to Loki. Charm logs (`juju debug-log` output) ship automatically via the same relation. Configurable log levels via the existing `log-level` charm config.

### Cross-Model Integration

COS deploys in a separate Juju model. Operators consume offers cross-model:

```bash
juju integrate <charm>:metrics-endpoint   admin/cos.prometheus
juju integrate <charm>:logging            admin/cos.loki
juju integrate <charm>:charm-tracing      admin/cos.tempo
juju integrate <charm>:grafana-dashboard  admin/cos.grafana
```

The crowsnest charm relates the same way. Documentation walks operators through this once; no bundle automation.

### Per-Charm Scope

This ADR establishes the per-charm contract. The charmarr-crowsnest-k8s charm's specific responsibilities are detailed in [adr-003](adr-003-dashboards-and-alerts.md) and [adr-004](adr-004-sli-slo-strategy.md).

## Consequences

### Good

- **Zero coupling to COS lifecycle.** Charmarr deploys, upgrades, and operates without ever knowing whether COS exists. Same model as Istio.
- **Per-charm granularity.** Operators can wire metrics from one charm and not another. Useful for staged rollouts and selective monitoring.
- **All COS flavors work.** `cos-lite` users get metrics + logs, `cos`/`cos-dev` users additionally get traces. The `tracing` relation simply doesn't bind on `cos-lite`.
- **Standard interfaces only.** No charmarr-invented observability interfaces. Operators can swap charmarr for anything else without retraining.
- **Future-proof for Sloth and friends.** Standard relations let downstream tools (Sloth for SLOs, any APM, custom dashboards) plug in without charmarr work.

### Bad

- **Operator burden for cross-model integration.** ~4 `juju integrate` commands per charm. Mitigated by documentation and the fact that operators can script this themselves.
- **No bundled "everything works out of the box."** A user who doesn't read the docs sees no metrics. Mitigated by the deprecation/migration UX pattern we already use (loud status messages where relevant).

### Neutral

- **Crowsnest charm adds one more thing to deploy.** Single replica, low resource footprint. Optional — operators can skip it and still get per-charm observability.

## Related ADRs

- [adr-002-exporter-strategy.md](adr-002-exporter-strategy.md) — per-app exporter picks
- [adr-003-dashboards-and-alerts.md](adr-003-dashboards-and-alerts.md) — dashboard delivery, alert baseline
- [adr-004-sli-slo-strategy.md](adr-004-sli-slo-strategy.md) — SLI/SLO ownership and Sloth integration
- [adr-005-gluetun-metrics-shim.md](adr-005-gluetun-metrics-shim.md) — the one custom exporter we own
