output "model" {
  description = "Juju model name"
  value       = var.model
}

output "model_uuid" {
  description = "Juju model UUID"
  value       = data.juju_model.model.uuid
}

output "applications" {
  description = "Map of deployed application names"
  value = {
    storage      = module.storage.app_name
    gluetun      = module.gluetun.app_name
    qbittorrent  = module.qbittorrent.app_name
    sabnzbd      = module.sabnzbd.app_name
    prowlarr     = module.prowlarr.app_name
    flaresolverr = module.flaresolverr.app_name
    radarr_hd    = module.radarr_hd.app_name
    radarr_uhd   = module.radarr_uhd.app_name
    radarr_anime = module.radarr_anime.app_name
    sonarr_hd    = module.sonarr_hd.app_name
    sonarr_uhd   = module.sonarr_uhd.app_name
    sonarr_anime = module.sonarr_anime.app_name
    plex         = module.plex.app_name
    overseerr    = module.overseerr.app_name
  }
}

output "istio" {
  description = "Map of Istio application names"
  value = {
    control_plane = module.istio.app_name
    beacon        = module.beacon.app_name
  }
}

output "ingress" {
  description = "Map of ingress application names"
  value = {
    arr       = module.arr_ingress.app_name
    plex      = module.plex_ingress.app_name
    overseerr = module.overseerr_ingress.app_name
  }
}
