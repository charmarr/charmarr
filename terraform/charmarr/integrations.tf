# =============================================================================
# Locals — fleet maps consumed by for_each integrations below.
# =============================================================================

locals {
  # Fleet members with full o11y participation (metrics/logs/traces/crowsnest).
  # Conditional members merged in based on their enable_X flags.
  fleet = merge(
    {
      storage = {
        name     = module.storage.app_name
        provides = module.storage.provides
        requires = module.storage.requires
      }
      flaresolverr = {
        name     = module.flaresolverr.app_name
        provides = module.flaresolverr.provides
        requires = module.flaresolverr.requires
      }
      plex = {
        name     = module.plex.app_name
        provides = module.plex.provides
        requires = module.plex.requires
      }
      prowlarr = {
        name     = module.prowlarr.app_name
        provides = module.prowlarr.provides
        requires = module.prowlarr.requires
      }
      qbittorrent = {
        name     = module.qbittorrent.app_name
        provides = module.qbittorrent.provides
        requires = module.qbittorrent.requires
      }
      sabnzbd = {
        name     = module.sabnzbd.app_name
        provides = module.sabnzbd.provides
        requires = module.sabnzbd.requires
      }
      radarr = {
        name     = module.radarr.app_name
        provides = module.radarr.provides
        requires = module.radarr.requires
      }
      sonarr = {
        name     = module.sonarr.app_name
        provides = module.sonarr.provides
        requires = module.sonarr.requires
      }
    },
    var.enable_vpn ? {
      gluetun = {
        name     = module.gluetun[0].app_name
        provides = module.gluetun[0].provides
        requires = module.gluetun[0].requires
      }
    } : {},
    var.enable_seerr ? {
      seerr = {
        name     = module.seerr[0].app_name
        provides = module.seerr[0].provides
        requires = module.seerr[0].requires
      }
    } : {},
  )

  # Fleet + crowsnest, used for o11y signal emission (otelcol scrapes, grafana
  # dashboards). Only populated when cos != null.
  o11y_emitters = var.cos != null ? merge(
    local.fleet,
    {
      crowsnest = {
        name     = module.crowsnest[0].app_name
        provides = module.crowsnest[0].provides
        requires = module.crowsnest[0].requires
      }
    }
  ) : {}

  # Apps that consume media-manager (request charm or end-user player).
  # Tracked separately because overseerr lacks the full o11y endpoint set
  # and isn't included in local.fleet.
  media_consumers = merge(
    {
      plex = {
        name     = module.plex.app_name
        requires = module.plex.requires
      }
    },
    var.enable_overseerr ? {
      overseerr = {
        name     = module.overseerr[0].app_name
        requires = module.overseerr[0].requires
      }
    } : {},
    var.enable_seerr ? {
      seerr = {
        name     = module.seerr[0].app_name
        requires = module.seerr[0].requires
      }
    } : {},
  )

  # Arrs that provide media-manager.
  media_providers = {
    radarr = {
      name     = module.radarr.app_name
      provides = module.radarr.provides
    }
    sonarr = {
      name     = module.sonarr.app_name
      provides = module.sonarr.provides
    }
  }

  # Cartesian product of arr × consumer for media-manager wiring.
  media_manager_pairs = merge([
    for arr_k, arr_v in local.media_providers : {
      for con_k, con_v in local.media_consumers :
      "${arr_k}_${con_k}" => { arr = arr_v, consumer = con_v }
    }
  ]...)
}

# =============================================================================
# Storage Integrations
# =============================================================================

resource "juju_integration" "storage" {
  for_each = {
    for k, v in local.fleet :
    k => v if contains(keys(v.requires), "media_storage")
  }
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = each.value.name
    endpoint = each.value.requires.media_storage
  }
}

# =============================================================================
# VPN Integrations
# =============================================================================

resource "juju_integration" "vpn" {
  for_each = var.enable_vpn ? {
    for k, v in local.fleet :
    k => v if contains(keys(v.requires), "vpn_gateway")
  } : {}
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.gluetun[0].app_name
    endpoint = module.gluetun[0].provides.vpn_gateway
  }

  application {
    name     = each.value.name
    endpoint = each.value.requires.vpn_gateway
  }
}

# =============================================================================
# Indexer Integrations
# =============================================================================

resource "juju_integration" "indexer" {
  for_each = {
    for k, v in local.fleet :
    k => v if contains(keys(v.requires), "media_indexer")
  }
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = each.value.name
    endpoint = each.value.requires.media_indexer
  }
}

resource "juju_integration" "flaresolverr_prowlarr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.flaresolverr.app_name
    endpoint = module.flaresolverr.provides.flaresolverr
  }

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.requires.flaresolverr
  }
}

# =============================================================================
# Media Manager Integrations
# =============================================================================

resource "juju_integration" "media_manager" {
  for_each   = local.media_manager_pairs
  model_uuid = data.juju_model.model.uuid

  application {
    name     = each.value.arr.name
    endpoint = each.value.arr.provides.media_manager
  }

  application {
    name     = each.value.consumer.name
    endpoint = each.value.consumer.requires.media_manager
  }
}

# =============================================================================
# Media Server Integrations
# =============================================================================

resource "juju_integration" "media_server" {
  for_each = {
    for k, v in local.media_consumers :
    k => v if contains(keys(v.requires), "media_server")
  }
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.plex.app_name
    endpoint = module.plex.provides.media_server
  }

  application {
    name     = each.value.name
    endpoint = each.value.requires.media_server
  }
}

# =============================================================================
# Service Mesh Integrations
# =============================================================================

resource "juju_integration" "mesh" {
  for_each   = var.enable_mesh ? local.fleet : {}
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = each.value.name
    endpoint = each.value.requires.service_mesh
  }
}

resource "juju_integration" "mesh_overseerr" {
  count      = var.enable_mesh && var.enable_overseerr ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.overseerr[0].app_name
    endpoint = module.overseerr[0].requires.service_mesh
  }
}

resource "juju_integration" "mesh_otelcol" {
  count      = var.cos != null && var.enable_mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "service-mesh"
  }
}

resource "juju_integration" "mesh_crowsnest" {
  count      = var.cos != null && var.enable_mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.crowsnest[0].app_name
    endpoint = module.crowsnest[0].requires.service_mesh
  }
}

# =============================================================================
# Ingress Integrations
# =============================================================================

# arr_ingress fronts every fleet charm that ingresses except plex (plex_ingress)
# and seerr (seerr_ingress).
resource "juju_integration" "arr_ingress" {
  for_each = var.enable_istio ? {
    for k, v in local.fleet :
    k => v if contains(keys(v.requires), "istio_ingress_route") && !contains(["plex", "seerr"], k)
  } : {}
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress[0].app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = each.value.name
    endpoint = each.value.requires.istio_ingress_route
  }
}

resource "juju_integration" "plex_ingress_plex" {
  count      = var.enable_istio ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.plex_ingress[0].app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.istio_ingress_route
  }
}

resource "juju_integration" "overseerr_ingress_overseerr" {
  count      = var.enable_istio && var.enable_overseerr ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.overseerr_ingress[0].app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.overseerr[0].app_name
    endpoint = module.overseerr[0].requires.istio_ingress_route
  }
}

resource "juju_integration" "seerr_ingress_seerr" {
  count      = var.enable_istio && var.enable_seerr ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.seerr_ingress[0].app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.seerr[0].app_name
    endpoint = module.seerr[0].requires.istio_ingress_route
  }
}

# =============================================================================
# Observability — Crowsnest Fleet (gated on var.cos != null)
# =============================================================================

resource "juju_integration" "crowsnest_fleet" {
  for_each   = var.cos != null ? local.fleet : {}
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.crowsnest[0].app_name
    endpoint = module.crowsnest[0].requires.crowsnest
  }

  application {
    name     = each.value.name
    endpoint = each.value.provides.crowsnest
  }
}

# =============================================================================
# Observability — Otelcol scrapes (metrics, logs, traces)
# =============================================================================

resource "juju_integration" "otelcol_metrics" {
  for_each = {
    for k, v in local.o11y_emitters :
    k => v if contains(keys(v.provides), "metrics_endpoint")
  }
  model_uuid = data.juju_model.model.uuid

  application {
    name     = each.value.name
    endpoint = each.value.provides.metrics_endpoint
  }

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "metrics-endpoint"
  }
}

resource "juju_integration" "otelcol_logging" {
  for_each = {
    for k, v in local.o11y_emitters :
    k => v if contains(keys(v.requires), "logging")
  }
  model_uuid = data.juju_model.model.uuid

  application {
    name     = each.value.name
    endpoint = each.value.requires.logging
  }

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "receive-loki-logs"
  }
}

resource "juju_integration" "otelcol_tracing" {
  for_each = {
    for k, v in local.o11y_emitters :
    k => v if contains(keys(v.requires), "charm_tracing")
  }
  model_uuid = data.juju_model.model.uuid

  application {
    name     = each.value.name
    endpoint = each.value.requires.charm_tracing
  }

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "receive-traces"
  }
}

# =============================================================================
# Observability — Grafana SAAS dashboards + datasource
# =============================================================================

resource "juju_integration" "grafana_dashboard" {
  for_each = {
    for k, v in local.o11y_emitters :
    k => v if contains(keys(v.provides), "grafana_dashboard")
  }
  model_uuid = data.juju_model.model.uuid

  application {
    name     = each.value.name
    endpoint = each.value.provides.grafana_dashboard
  }

  application {
    offer_url = data.juju_offer.cos_grafana[0].url
  }
}

resource "juju_integration" "grafana_source_crowsnest" {
  count      = var.cos != null ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.crowsnest[0].app_name
    endpoint = module.crowsnest[0].provides.grafana_source
  }

  application {
    offer_url = data.juju_offer.cos_grafana[0].url
  }
}

# =============================================================================
# Observability — Otelcol → COS SAAS forwarders
# =============================================================================

resource "juju_integration" "otelcol_to_loki" {
  count      = var.cos != null ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "send-loki-logs"
  }

  application {
    offer_url = data.juju_offer.cos_loki_logging[0].url
  }
}

resource "juju_integration" "otelcol_to_mimir" {
  count      = var.cos != null ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "send-remote-write"
  }

  application {
    offer_url = data.juju_offer.cos_mimir_remote_write[0].url
  }
}

resource "juju_integration" "otelcol_to_tempo" {
  count      = var.cos != null ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "send-traces"
  }

  application {
    offer_url = data.juju_offer.cos_tempo_tracing[0].url
  }
}

resource "juju_integration" "otelcol_receive_ca_cert" {
  count      = var.cos != null ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = juju_application.otelcol[0].name
    endpoint = "receive-ca-cert"
  }

  application {
    offer_url = data.juju_offer.cos_send_ca_cert[0].url
  }
}

# Cross-model mesh trust for the grafana SAAS — needed so istio's
# AuthorizationPolicy permits grafana traffic into crowsnest.
resource "juju_integration" "crowsnest_grafana_cmr_mesh" {
  count      = var.cos != null && var.enable_mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.crowsnest[0].app_name
    endpoint = module.crowsnest[0].provides.provide_cmr_mesh
  }

  application {
    offer_url = data.juju_offer.cos_grafana[0].url
  }
}
