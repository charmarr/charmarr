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
    gluetun      = var.enable_vpn ? module.gluetun[0].app_name : null
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
    plex         = local.enable_plex ? module.plex[0].app_name : null
    jellyfin     = local.enable_jellyfin ? module.jellyfin[0].app_name : null
    overseerr    = var.enable_overseerr ? module.overseerr[0].app_name : null
    seerr        = var.enable_seerr ? module.seerr[0].app_name : null
  }
}

output "mesh" {
  description = "Name of the istio-beacon application, or null when enable_istio = false"
  value       = var.enable_istio ? module.beacon[0].app_name : null
}

output "ingress" {
  description = "Ingress provider in use and the application names it fronts with"
  value = {
    provider = var.enable_istio ? "istio-ingress-k8s" : "traefik-k8s"
    arr      = local.arr_ingress_app
    plex     = local.plex_ingress_app
    jellyfin = local.jellyfin_ingress_app
    seerr    = local.seerr_ingress_app
  }
}
