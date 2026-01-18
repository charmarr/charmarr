# -----------------------------------------------------------------------------
# Storage Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "storage_qbittorrent" {
  model = var.model

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
  model = var.model

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.sabnzbd.app_name
    endpoint = module.sabnzbd.requires.media_storage
  }
}

resource "juju_integration" "storage_radarr" {
  model = var.model

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.radarr.app_name
    endpoint = module.radarr.requires.media_storage
  }
}

resource "juju_integration" "storage_sonarr" {
  model = var.model

  application {
    name     = module.storage.app_name
    endpoint = module.storage.provides.media_storage
  }

  application {
    name     = module.sonarr.app_name
    endpoint = module.sonarr.requires.media_storage
  }
}

resource "juju_integration" "storage_plex" {
  model = var.model

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
  model = var.model

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
  model = var.model

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
  model = var.model

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

resource "juju_integration" "prowlarr_radarr" {
  model = var.model

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.radarr.app_name
    endpoint = module.radarr.requires.media_indexer
  }
}

resource "juju_integration" "prowlarr_sonarr" {
  model = var.model

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.provides.media_indexer
  }

  application {
    name     = module.sonarr.app_name
    endpoint = module.sonarr.requires.media_indexer
  }
}

resource "juju_integration" "flaresolverr_prowlarr" {
  model = var.model

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

resource "juju_integration" "radarr_overseerr" {
  model = var.model

  application {
    name     = module.radarr.app_name
    endpoint = module.radarr.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "radarr_plex" {
  model = var.model

  application {
    name     = module.radarr.app_name
    endpoint = module.radarr.provides.media_manager
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.media_manager
  }
}

resource "juju_integration" "sonarr_overseerr" {
  model = var.model

  application {
    name     = module.sonarr.app_name
    endpoint = module.sonarr.provides.media_manager
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.media_manager
  }
}

resource "juju_integration" "sonarr_plex" {
  model = var.model

  application {
    name     = module.sonarr.app_name
    endpoint = module.sonarr.provides.media_manager
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
  model = var.model

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
# Ingress Integrations
# -----------------------------------------------------------------------------

resource "juju_integration" "arr_ingress_radarr" {
  model = var.model

  application {
    name     = module.arr_ingress.app_name
    endpoint = "ingress"
  }

  application {
    name     = module.radarr.app_name
    endpoint = module.radarr.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_sonarr" {
  model = var.model

  application {
    name     = module.arr_ingress.app_name
    endpoint = "ingress"
  }

  application {
    name     = module.sonarr.app_name
    endpoint = module.sonarr.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_prowlarr" {
  model = var.model

  application {
    name     = module.arr_ingress.app_name
    endpoint = "ingress"
  }

  application {
    name     = module.prowlarr.app_name
    endpoint = module.prowlarr.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_qbittorrent" {
  model = var.model

  application {
    name     = module.arr_ingress.app_name
    endpoint = "ingress"
  }

  application {
    name     = module.qbittorrent.app_name
    endpoint = module.qbittorrent.requires.istio_ingress_route
  }
}

resource "juju_integration" "arr_ingress_sabnzbd" {
  model = var.model

  application {
    name     = module.arr_ingress.app_name
    endpoint = "ingress"
  }

  application {
    name     = module.sabnzbd.app_name
    endpoint = module.sabnzbd.requires.istio_ingress_route
  }
}

resource "juju_integration" "plex_ingress_plex" {
  model = var.model

  application {
    name     = module.plex_ingress.app_name
    endpoint = "ingress"
  }

  application {
    name     = module.plex.app_name
    endpoint = module.plex.requires.istio_ingress_route
  }
}

resource "juju_integration" "overseerr_ingress_overseerr" {
  model = var.model

  application {
    name     = module.overseerr_ingress.app_name
    endpoint = "ingress"
  }

  application {
    name     = module.overseerr.app_name
    endpoint = module.overseerr.requires.istio_ingress_route
  }
}
