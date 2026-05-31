# Observability

![Charmarr fleet dashboard](../assets/screenshots/fleet-dashboard.png)

Charmarr is designed from the ground up to integrate with the [Canonical Observability Stack (COS)](https://documentation.ubuntu.com/observability/track-2/). Every charm bundles its own Prometheus exporter, a curated Grafana dashboard, and alert rules. Wire it to COS and you get metrics, logs, traces, and per-app dashboards out of the box. No exporter hunting. No dashboard scavenging. No glue code.

COS is itself a charmed, open-source observability bundle. It ships:

* **Mimir** for metrics
* **Loki** for logs
* **Tempo** for traces
* **Grafana** for dashboards and datasources
* **AlertManager** for routing alerts
* **OpenTelemetry Collector** as the telemetry ingress

Charmarr plugs into all five via standard Juju relations.

<div class="grid cards" markdown>

-   **Enable**

    ---

    One Terraform variable, or a handful of `juju integrate` commands.

    [:octicons-arrow-right-24: Setup](enable.md)

-   **Dashboards**

    ---

    Per-charm Grafana dashboards shipped with every charm. Zero ops.

    [:octicons-arrow-right-24: Per-charm dashboards](dashboards.md)

-   **Crowsnest**

    ---

    Workloadless fleet observability charm: relation graph, SLOs, alerts.

    [:octicons-arrow-right-24: Crowsnest](crowsnest.md)

</div>

## What you get out of the box

| Concern | Vanilla K8s | Charmarr + COS |
|---|---|---|
| Per-app exporter | Find, deploy, configure manually | Bundled in the charm sidecar |
| Per-app dashboard | Hunt on Grafana.com, import, tweak | Ships with the charm, auto-imported |
| Alert rules | Author or copy-paste | Curated per charm, auto-published |
| Metrics pipeline | Wire Prometheus or OTel by hand | One `juju integrate` |
| Logs pipeline | Promtail, Fluent, or OTel by hand | One `juju integrate` |
| Traces pipeline | OTel collector by hand | One `juju integrate` |
| Fleet topology graph | Build it yourself | Crowsnest does it |

Hours of ops work collapsed into a relation.

!!! warning "Only COS is officially supported"
    These docs cover COS only. Other backends are not documented and not officially supported. If you want to forward telemetry to a non-COS backend (Grafana Cloud, Signoz, Datadog, VictoriaMetrics, any OTLP target), it is technically possible by deploying [`opentelemetry-collector-k8s`](https://charmhub.io/opentelemetry-collector-k8s) in the charmarr model and configuring it as a forwarder. You give up auto-imported dashboards and auto-loaded alert rules. Experiments are welcome and PRs adding documented support for additional backends are encouraged.

!!! note "COS itself is not covered here"
    Deploying and operating COS is out of scope. See the [official COS documentation](https://documentation.ubuntu.com/observability/track-2/) for installation, scaling, retention tuning, and high-availability patterns.
