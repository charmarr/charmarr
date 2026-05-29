# SLI / SLO Strategy

## Context and Problem Statement

[ADR-003](adr-003-dashboards-and-alerts.md) commits cheap-win threshold alerts as the baseline. Threshold alerts are noisy and don't capture user-visible service quality. We want proper Service Level Objectives — multi-burn-rate alerting on user-meaningful indicators — without reinventing infrastructure that already exists in the COS ecosystem.

Canonical maintains `sloth-k8s`, an operator that converts declarative SLO specifications into Prometheus recording rules and multi-burn-rate alert rules following the Google SRE Workbook methodology. It integrates with COS via standard relations (`prometheus_remote_write`, `grafana_dashboard`) and consumes SLO specs from app charms via a `sloth` interface.

**Key constraints:**
- We do not write multi-burn-rate alerting logic ourselves. Sloth does it correctly.
- SLI metrics — the underlying "good event vs bad event" counters — must exist as Prometheus timeseries before any SLO can reference them.
- Sloth integration must be optional. Charmarr deployments without Sloth still benefit from the underlying SLI metrics.
- SLO definitions belong in version control as data, not generated dynamically.

## Considered Options

### SLO Compute Ownership
* **Option 1:** Charmarr-crowsnest writes Prometheus recording rules and burn-rate alerts directly.
* **Option 2:** Charmarr provides declarative SLO specs to Sloth; Sloth generates the rules.

### Where SLO Specs Live
* **Option 1:** Hardcoded in `charm.py` as Python data structures.
* **Option 2:** YAML files in `src/slos/` parsed at runtime.
* **Option 3:** Charm config option allowing operators to override SLO specs.

### Per-Charm vs Crowsnest-Only SLO Ownership
* **Option 1:** Every charm provides its own SLOs via its own Sloth relation.
* **Option 2:** Only charmarr-crowsnest provides SLO specs; per-charm SLOs are bundled in the central catalog.

## Decision Outcome

**SLO compute: Option 2** — Charmarr-crowsnest provides SLO specs through the `sloth` interface. Sloth generates the recording rules and burn-rate alerts. This avoids reimplementing well-understood SRE primitives.

**SLO specs: Option 2** — YAML files in `src/slos/`. The crowsnest charm reads, validates (via `charmlibs.interfaces.sloth.SLOSpec` Pydantic model), and publishes via the relation at reconcile. Operators can fork and re-charm if they need overrides; we don't expose runtime override config (keeps the data plane clean).

**SLO ownership: Option 2** — Crowsnest is the sole provider of charmarr's SLO catalog. Per-charm SLO management would fragment the spec across many charms and prevent the cross-cutting SLOs (e.g., end-to-end request fulfillment) from existing anywhere. Crowsnest has the topology view; it's the natural place.

## Implementation Details

### The SLO Catalog

Crowsnest ships SLOs grouped by domain in `src/slos/`:

| File | SLOs | Why this domain |
|---|---|---|
| `requests.yaml` | request-fulfillment-availability, request-fulfillment-latency | User-visible: "I requested a movie, did it arrive?" |
| `downloads.yaml` | download-completion-success, download-throughput | Stack reliability: "Is the data path working?" |
| `availability.yaml` | media-server-availability, stack-up | "Are my apps actually serving?" |
| `vpn.yaml` | vpn-tunnel-availability | Privacy/safety: "Did my downloads leak my real IP?" |
| `indexer.yaml` | indexer-success-rate | Hidden plumbing: "Are searches working?" |

### Example SLO Spec

```yaml
# src/slos/requests.yaml
version: "prometheus/v1"
service: "charmarr-requests"
labels:
  stack: charmarr
slos:
  - name: request-fulfillment-availability
    objective: 99.0
    description: |
      99% of media requests submitted via Seerr should reach the
      "available" state (file imported, library refreshed).
    sli:
      events:
        error_query: |
          sum(rate(charmarr_request_fulfillment_failures_total[{{.window}}]))
        total_query: |
          sum(rate(charmarr_request_fulfillment_total[{{.window}}]))
    alerting:
      name: CharmarrRequestFulfillmentBudgetBurn
      labels:
        category: user-experience
      page_alert:
        labels: {severity: page}
      ticket_alert:
        labels: {severity: ticket}
```

### SLI Metrics — Who Produces Them

The underlying counters and histograms feeding SLI queries are produced by crowsnest's own in-pod exporter. The exporter watches relation data from every charmarr charm and emits derived metrics on `/metrics`:

| SLI Metric | Derivation source |
|---|---|
| `charmarr_request_fulfillment_total{requester, manager}` | Seerr API → Radarr/Sonarr history → file system poll |
| `charmarr_request_fulfillment_failures_total{requester, manager, reason}` | Same, with failure classification |
| `charmarr_request_fulfillment_seconds_bucket{requester, manager}` | Histogram of fulfillment latency |
| `charmarr_download_completion_total{client}` | qBit/SAB API → completed torrent/nzb count |
| `charmarr_download_failures_total{client, reason}` | Same with failure events |
| `charmarr_media_server_health` | Plex API ping status |
| `charmarr_stack_up_total` | Count of charmarr charms in `active` status from juju status data |
| `charmarr_vpn_tunnel_up` | Gluetun shim status (see [adr-005](adr-005-gluetun-metrics-shim.md)) |
| `charmarr_indexer_query_success_total{indexer}` | Prowlarr API → indexer stats |

These metrics exist independently of Sloth being deployed. A user on `cos-lite` without Sloth gets the underlying SLI timeseries; they just don't get burn-rate alerts or SLO dashboards automatically.

### The `sloth` Relation

```yaml
# charmarr-crowsnest-k8s/charmcraft.yaml
provides:
  sloth:
    interface: sloth
    optional: true
    description: |
      SLO specifications for the charmarr stack. When related to a
      Sloth deployment, generates Prometheus recording rules and
      multi-burn-rate alerts.
```

The charm uses `charmlibs.interfaces.sloth.SlothProvider`:

```python
from charmlibs.interfaces.sloth import SlothProvider, SLOSpec
import yaml

class CrowsnestCharm(ops.CharmBase):
    def __init__(self, framework):
        super().__init__(framework)
        self._sloth = SlothProvider(self)
        framework.observe(self.on.config_changed, self._reconcile)

    def _publish_slos(self):
        specs = []
        for path in (self.charm_dir / "src/slos").glob("*.yaml"):
            with path.open() as f:
                data = yaml.safe_load(f)
            specs.append(SLOSpec(**data))
        self._sloth.publish(specs)
```

The library handles topology label injection (juju_application, juju_model) into the SLI queries automatically.

### Lifecycle Without Sloth

Operators without Sloth see:
- ✓ Underlying SLI metrics in Prometheus (`charmarr_request_fulfillment_*` etc.)
- ✓ Per-charm dashboards from each charm
- ✓ Cross-cutting dashboards from crowsnest
- ✓ Cheap-win alerts from each charm
- ✓ Stack-level alerts from crowsnest
- ✗ Burn-rate SLO alerts
- ✗ SLO compliance dashboards

The metrics are still useful — operators can hand-write their own dashboards/alerts against them. Sloth integration is purely a convenience over the same data.

### Lifecycle With Sloth

Operator runs:
```bash
juju deploy sloth-k8s sloth --channel=edge
juju integrate crowsnest:sloth sloth:sloth
juju integrate sloth:remote-write admin/cos.prometheus
juju integrate sloth:grafana-dashboard admin/cos.grafana
```

Sloth picks up the seven SLO specs, generates ~30 Prometheus recording rules and ~14 multi-burn-rate alerts, registers ~7 Grafana dashboards. All without further charmarr work.

### Versioning the SLO Specs

The SLO YAMLs are part of crowsnest's source tree, versioned alongside the charm. Changing an SLO objective is a charm change, goes through CI, ships through Charmhub revisions. Operators get the same upgrade path as for any other charm.

This is intentional — SLO objectives encode an operational contract; runtime override would let production drift from the documented design.

## Consequences

### Good

- **No reinvented SRE primitives.** Burn-rate alerting is a hard problem solved correctly by Sloth.
- **Clean SLI/SLO separation.** Charmarr owns event semantics ("what counts as a failure"); Sloth owns objective semantics ("99% over 30d").
- **Optional Sloth.** Users without it still get SLI metrics; the upgrade to Sloth is purely additive.
- **Spec-as-code.** SLO definitions are reviewable, diff'able, version-controlled.
- **Topology-correct out of the box.** Sloth interface injects juju labels so multi-deployment Grafana works.

### Bad

- **Two-charm dependency for the full SLO experience.** Crowsnest + Sloth. Mitigated by the optional pattern.
- **SLI metric implementation effort.** Producing `charmarr_request_fulfillment_seconds_bucket` requires real cross-app event correlation in crowsnest, not just static config. Implementation work but not architectural complexity.

### Neutral

- **No runtime SLO override knob.** Operators wanting different objectives fork. Acceptable for v1; revisit if user demand materializes.

## Related ADRs

- [adr-001-cos-integration-architecture.md](adr-001-cos-integration-architecture.md) — relation contract
- [adr-002-exporter-strategy.md](adr-002-exporter-strategy.md) — per-app metrics that feed SLIs
- [adr-003-dashboards-and-alerts.md](adr-003-dashboards-and-alerts.md) — non-SLO dashboards and cheap-win alerts
- [adr-005-gluetun-metrics-shim.md](adr-005-gluetun-metrics-shim.md) — the `charmarr_vpn_tunnel_up` source
