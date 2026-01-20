# -----------------------------------------------------------------------------
# Storage Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "storage_qbittorrent" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.qbittorrent.app_name
    endpoint = module.qbittorrent.requires.media_storage
  }
}

resource "juju_integration" "storage_sabnzbd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.sabnzbd.app_name
    endpoint = module.sabnzbd.requires.media_storage
  }
}

resource "juju_integration" "storage_radarr_hd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.radarr_hd.app_name
    endpoint = module.radarr_hd.requires.media_storage
  }
}

resource "juju_integration" "storage_radarr_uhd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.radarr_uhd.app_name
    endpoint = module.radarr_uhd.requires.media_storage
  }
}

resource "juju_integration" "storage_radarr_anime" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.radarr_anime.app_name
    endpoint = module.radarr_anime.requires.media_storage
  }
}

resource "juju_integration" "storage_sonarr_hd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.sonarr_hd.app_name
    endpoint = module.sonarr_hd.requires.media_storage
  }
}

resource "juju_integration" "storage_sonarr_uhd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.sonarr_uhd.app_name
    endpoint = module.sonarr_uhd.requires.media_storage
  }
}

resource "juju_integration" "storage_sonarr_anime" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.sonarr_anime.app_name
    endpoint = module.sonarr_anime.requires.media_storage
  }
}

resource "juju_integration" "storage_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_storage
  }
}

# -----------------------------------------------------------------------------
# VPN Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "gluetun_qbittorrent" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.gluetun.app_name
    endpoint = module.gluetun.provides.vpn_gateway
  }

  application {
    name     = module.qbittorrent.app_name
    endpoint = module.qbittorrent.requires.vpn_gateway
  }
}

resource "juju_integration" "gluetun_sabnzbd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.gluetun.app_name
    endpoint = module.gluetun.provides.vpn_gateway
  }

  application {
    name     = module.sabnzbd.app_name
    endpoint = module.sabnzbd.requires.vpn_gateway
  }
}

resource "juju_integration" "gluetun_prowlarr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.gluetun.app_name
    endpoint = module.gluetun.provides.vpn_gateway
  }

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.requires.vpn_gateway
  }
}

# -----------------------------------------------------------------------------
# Indexer Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "prowlarr_radarr_hd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.radarr_hd.app_name
    endpoint = module.radarr_hd.requires.media_indexer
  }
}

resource "juju_integration" "prowlarr_radarr_uhd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.radarr_uhd.app_name
    endpoint = module.radarr_uhd.requires.media_indexer
  }
}

resource "juju_integration" "prowlarr_radarr_anime" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.radarr_anime.app_name
    endpoint = module.radarr_anime.requires.media_indexer
  }
}

resource "juju_integration" "prowlarr_sonarr_hd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.sonarr_hd.app_name
    endpoint = module.sonarr_hd.requires.media_indexer
  }
}

resource "juju_integration" "prowlarr_sonarr_uhd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.sonarr_uhd.app_name
    endpoint = module.sonarr_uhd.requires.media_indexer
  }
}

resource "juju_integration" "prowlarr_sonarr_anime" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.sonarr_anime.app_name
    endpoint = module.sonarr_anime.requires.media_indexer
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

# -----------------------------------------------------------------------------
# Media Manager Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "radarr_hd_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.radarr_hd.app_name
    endpoint = module.radarr_hd.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "radarr_uhd_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.radarr_uhd.app_name
    endpoint = module.radarr_uhd.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "radarr_anime_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.radarr_anime.app_name
    endpoint = module.radarr_anime.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "radarr_hd_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.radarr_hd.app_name
    endpoint = module.radarr_hd.provides.media_manager
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_manager
  }
}

resource "juju_integration" "radarr_uhd_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.radarr_uhd.app_name
    endpoint = module.radarr_uhd.provides.media_manager
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_manager
  }
}

resource "juju_integration" "radarr_anime_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.radarr_anime.app_name
    endpoint = module.radarr_anime.provides.media_manager
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_manager
  }
}

resource "juju_integration" "sonarr_hd_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.sonarr_hd.app_name
    endpoint = module.sonarr_hd.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "sonarr_uhd_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.sonarr_uhd.app_name
    endpoint = module.sonarr_uhd.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "sonarr_anime_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.sonarr_anime.app_name
    endpoint = module.sonarr_anime.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "sonarr_hd_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.sonarr_hd.app_name
    endpoint = module.sonarr_hd.provides.media_manager
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_manager
  }
}

resource "juju_integration" "sonarr_uhd_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.sonarr_uhd.app_name
    endpoint = module.sonarr_uhd.provides.media_manager
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_manager
  }
}

resource "juju_integration" "sonarr_anime_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.sonarr_anime.app_name
    endpoint = module.sonarr_anime.provides.media_manager
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_manager
  }
}

# -----------------------------------------------------------------------------
# Media Server Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "plex_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.plex.app_name
    endpoint = module.plex.provides.media_server
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_server
  }
}

# -----------------------------------------------------------------------------
# Service Mesh Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "beacon_qbittorrent" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.qbittorrent.app_name
    endpoint = module.qbittorrent.requires.service_mesh
  }
}

resource "juju_integration" "beacon_sabnzbd" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.sabnzbd.app_name
    endpoint = module.sabnzbd.requires.service_mesh
  }
}

resource "juju_integration" "beacon_prowlarr" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.requires.service_mesh
  }
}

resource "juju_integration" "beacon_radarr_hd" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.radarr_hd.app_name
    endpoint = module.radarr_hd.requires.service_mesh
  }
}

resource "juju_integration" "beacon_radarr_uhd" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.radarr_uhd.app_name
    endpoint = module.radarr_uhd.requires.service_mesh
  }
}

resource "juju_integration" "beacon_radarr_anime" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.radarr_anime.app_name
    endpoint = module.radarr_anime.requires.service_mesh
  }
}

resource "juju_integration" "beacon_sonarr_hd" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.sonarr_hd.app_name
    endpoint = module.sonarr_hd.requires.service_mesh
  }
}

resource "juju_integration" "beacon_sonarr_uhd" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.sonarr_uhd.app_name
    endpoint = module.sonarr_uhd.requires.service_mesh
  }
}

resource "juju_integration" "beacon_sonarr_anime" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.sonarr_anime.app_name
    endpoint = module.sonarr_anime.requires.service_mesh
  }
}

resource "juju_integration" "beacon_plex" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.service_mesh
  }
}

resource "juju_integration" "beacon_overseerr" {
  count      = var.mesh ? 1 : 0
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.beacon[0].app_name
    endpoint = "service-mesh"
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.service_mesh
  }
}

# -----------------------------------------------------------------------------
# Ingress Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "arr_ingress_radarr_hd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.radarr_hd.app_name
    endpoint = module.radarr_hd.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_radarr_uhd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.radarr_uhd.app_name
    endpoint = module.radarr_uhd.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_radarr_anime" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.radarr_anime.app_name
    endpoint = module.radarr_anime.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_sonarr_hd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.sonarr_hd.app_name
    endpoint = module.sonarr_hd.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_sonarr_uhd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.sonarr_uhd.app_name
    endpoint = module.sonarr_uhd.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_sonarr_anime" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.sonarr_anime.app_name
    endpoint = module.sonarr_anime.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_prowlarr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_qbittorrent" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.qbittorrent.app_name
    endpoint = module.qbittorrent.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_sabnzbd" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.arr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.sabnzbd.app_name
    endpoint = module.sabnzbd.requires.istio_ingress_route
  }
}

resource "juju_integration" "plex_ingress_plex" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.plex_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.istio_ingress_route
  }
}

resource "juju_integration" "overseerr_ingress_overseerr" {
  model_uuid = data.juju_model.model.uuid

  application {
    name     = module.overseerr_ingress.app_name
    endpoint = "istio-ingress-route"
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.istio_ingress_route
  }
}
