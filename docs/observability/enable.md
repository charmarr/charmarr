# Enable observability

Two paths: Terraform (recommended) or `juju` CLI. Both wire the same thing: an OpenTelemetry Collector in the charmarr model, the [`charmarr-crowsnest-k8s`](crowsnest.md) charm, and five integrations into the COS-side offers.

## Coverage per charm

Not every charm exposes every observability relation. Verified against the published `charmcraft.yaml` files.

| Charm | metrics | dashboard | logs | traces | crowsnest |
|---|:---:|:---:|:---:|:---:|:---:|
| charmarr-storage | ✅ | ✅ | ✅ | ✅ | ✅ |
| flaresolverr | ✅ | ✅ | ✅ | ✅ | ✅ |
| gluetun | ✅ | ✅ | ✅ | ✅ | ✅ |
| plex | ✅ | ✅ | ✅ | ✅ | ✅ |
| prowlarr | ✅ | ✅ | ✅ | ✅ | ✅ |
| qbittorrent | ✅ | ✅ | ✅ | ✅ | ✅ |
| radarr | ✅ | ✅ | ✅ | ✅ | ✅ |
| sabnzbd | ✅ | ✅ | ✅ | ✅ | ✅ |
| sonarr | ✅ | ✅ | ✅ | ✅ | ✅ |
| seerr | ✅ | ❌ | ❌ | ❌ | ✅ |
| overseerr | ❌ | ❌ | ❌ | ❌ | ❌ |

**Seerr** publishes a single metric, `charmarr_requests_total{status=...}`, which powers the fleet-level request funnel and SLO. It does not bundle a dashboard because seerr itself is already a UI for tracking the same data (pending, approved, processing, available, declined). The fleet view is the right place to look for request signal in Grafana.

**Overseerr** is deprecated. It carries no observability relations. The [migration runbook](../migration/overseerr-to-seerr.md) covers moving to seerr.

## Prerequisites

### COS offers

COS lives in a separate Juju model. Whoever owns the COS deployment must expose five offers:

| Offer | Charm | Endpoint |
|---|---|---|
| `grafana` | grafana | `grafana-dashboard`, `grafana-source` |
| `loki-logging` | loki | `logging` |
| `mimir-receive-remote-write` | mimir | `receive-remote-write` |
| `send-ca-cert` | grafana | `send-ca-cert` |
| `tempo-tracing` | tempo | `tracing` |

Typical pattern on the COS side:

```bash
juju offer grafana:grafana-dashboard,grafana-source -m cos
juju offer loki:logging -m cos
juju offer mimir-receive-remote-write:receive-remote-write -m cos
juju offer send-ca-cert:send-ca-cert -m cos
juju offer tempo:tracing -m cos
```

Adjust app names to match your COS deployment.

### Grafana node-graph plugin

The fleet relation graph in crowsnest's dashboard is rendered by the [`hamedkarbasi93-nodegraphapi-datasource`](https://grafana.com/grafana/plugins/hamedkarbasi93-nodegraphapi-datasource/) Grafana plugin. The plugin must be installed in the COS Grafana before the fleet dashboard panel will render.

Install it on the COS side with:

```bash
juju config grafana datasource_plugins="hamedkarbasi93-nodegraphapi-datasource" -m cos
```

Grafana will install the plugin and restart automatically.

## With Terraform

The bundled Terraform modules at [`terraform/charmarr/`](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr) and [`terraform/charmarr-plus/`](https://github.com/charmarr/charmarr/tree/main/terraform/charmarr-plus) take a single `cos` variable. When set, otelcol and crowsnest get deployed, every fleet relation wires automatically, and crowsnest is exposed through the existing arr-ingress so that COS reaches it via the external URL.

```hcl title="terraform.tfvars"
model = "charmarr"
owner = "admin"

# ... usual charmarr config ...

cos = {
  offers = {
    grafana            = "admin/cos.grafana"
    loki_logging       = "admin/cos.loki-logging"
    mimir_remote_write = "admin/cos.mimir-receive-remote-write"
    send_ca_cert       = "admin/cos.send-ca-cert"
    tempo_tracing      = "admin/cos.tempo-tracing"
  }
}
```

That is the entire observability configuration. `terraform apply` brings up the plane.

Leave `cos = null` (the default) and nothing observability-related is deployed.

!!! tip "Why ingress and not cross-model mesh"
    Grafana lives in the COS model and needs to reach crowsnest to render the fleet's relation graph. Wiring crowsnest into arr-ingress publishes a stable external URL that COS uses directly. No cross-model Istio policies. No mesh trust shenanigans. Cross-model access happens through ingress.

## With the Juju CLI

For users not on Terraform, the same wiring done by hand. Substitute your COS controller and model names where applicable.

### 1. Consume the COS offers

```bash
juju consume admin/cos.grafana -m charmarr
juju consume admin/cos.loki-logging -m charmarr
juju consume admin/cos.mimir-receive-remote-write -m charmarr
juju consume admin/cos.send-ca-cert -m charmarr
juju consume admin/cos.tempo-tracing -m charmarr
```

If COS lives on a different controller, use the cross-controller form: `juju consume <controller>:admin/cos.grafana`.

### 2. Deploy the local plane

```bash
juju deploy opentelemetry-collector-k8s otelcol --channel 2/edge --trust -m charmarr
juju deploy charmarr-crowsnest-k8s crowsnest --channel latest/edge --trust -m charmarr
```

### 3. Wire each charmarr charm to otelcol

For every fleet charm that exposes the relevant relation (refer to the coverage table above). Example with radarr:

```bash
# Metrics scrape
juju integrate radarr:metrics-endpoint otelcol:metrics-endpoint -m charmarr

# Log forwarding
juju integrate radarr:logging otelcol:receive-loki-logs -m charmarr

# Charm hook traces
juju integrate radarr:charm-tracing otelcol:receive-traces -m charmarr

# Dashboard publishing
juju integrate radarr:grafana-dashboard grafana -m charmarr
```

Same four lines for sonarr, prowlarr, qbittorrent, sabnzbd, plex, flaresolverr, gluetun, charmarr-storage, and crowsnest. For seerr, only the metrics relation applies:

```bash
juju integrate seerr:metrics-endpoint otelcol:metrics-endpoint -m charmarr
```

### 4. Wire the fleet relation

Crowsnest aggregates each fleet member's topology graph via the `crowsnest` relation:

```bash
for app in radarr sonarr prowlarr qbittorrent sabnzbd plex gluetun flaresolverr seerr charmarr-storage; do
  juju integrate crowsnest:crowsnest $app:crowsnest -m charmarr
done
```

### 5. Expose crowsnest via ingress

Grafana renders crowsnest's relation graph by fetching from its HTTP endpoint. Cross-model access happens through the existing istio-ingress charm, which avoids needing cross-model mesh policies:

```bash
juju integrate crowsnest:istio-ingress-route arr-ingress:istio-ingress-route -m charmarr
juju integrate crowsnest:grafana-source grafana -m charmarr
juju integrate crowsnest:grafana-dashboard grafana -m charmarr
```

The `grafana-source` relation publishes the external URL of crowsnest's HTTP endpoint, which Grafana uses as a datasource.

### 6. Wire otelcol to the COS offers

```bash
juju integrate otelcol:send-loki-logs loki-logging -m charmarr
juju integrate otelcol:send-remote-write mimir-receive-remote-write -m charmarr
juju integrate otelcol:send-traces tempo-tracing -m charmarr
juju integrate otelcol:receive-ca-cert send-ca-cert -m charmarr
```

## Verify

```bash
juju status -m charmarr
```

All units should reach `active` after a couple of minutes. Open Grafana, look for dashboards tagged `charmarr`, and the fleet view shows up under "Charmarr Fleet".
