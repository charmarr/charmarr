# Observability ADRs

Architecture Decision Records covering charmarr's integration with the Canonical Observability Stack (COS) and related tooling (Sloth).

## ADR Index

| ADR | Scope |
|-----|-------|
| [adr-001-cos-integration-architecture.md](adr-001-cos-integration-architecture.md) | Per-charm relation contract, deployment topology, dev/reference COS flavor (`cos-dev` monolithic) |
| [adr-002-exporter-strategy.md](adr-002-exporter-strategy.md) | Per-app Prometheus exporter picks, Pebble-service integration pattern, OCI layering |
| [adr-003-dashboards-and-alerts.md](adr-003-dashboards-and-alerts.md) | Per-charm vs crowsnest split, default alert baseline, dashboard layout |
| [adr-004-sli-slo-strategy.md](adr-004-sli-slo-strategy.md) | SLI metric ownership in crowsnest, SLO catalog, Sloth integration |
| [adr-005-gluetun-metrics-shim.md](adr-005-gluetun-metrics-shim.md) | Custom Python shim for Gluetun (the one exporter we own) |

## Key Concepts

- **Charmarr is COS-producer-only.** Users deploy and operate their own COS deployment. Charmarr ships standard relations (`prometheus_scrape`, `loki_push_api`, `tracing`, `grafana_dashboard`) and produces metrics, logs, traces, dashboards, and alert rules. Same pattern as Istio integration today.
- **Three pillars: metrics, logs, traces.** Every charm exposes all four observability relations. They are all `optional: true` — works against any COS flavor.
- **Per-charm signals + stack-level aggregator.** Each charm ships its own dashboard, alert rules, and exporter. The dedicated `charmarr-crowsnest-k8s` charm provides cross-cutting dashboards, fleet-level alerts, derived SLI metrics, and SLO specs for Sloth.
- **Sloth handles SLO compute.** Charmarr provides SLO specs as declarative YAML through the `sloth` interface; Sloth generates the multi-burn-rate recording and alert rules.
- **`cos-dev` monolithic mode is our development target.** Smallest footprint that includes all three pillars including tracing. Our docs do not recommend a COS flavor to users.

## Related Domains

- [apps/](../apps/) — Per-charm baseline ADRs; observability extends each charm's existing contract.
- [interfaces/](../interfaces/) — Relation interface design; observability uses standard Canonical interfaces.
- [networking/](../networking/) — Istio-emitted traces are part of the tracing story when ingress is enabled.
