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
    radarr       = module.radarr.app_name
    sonarr       = module.sonarr.app_name
    plex         = module.plex.app_name
    overseerr    = module.overseerr.app_name
  }
}

output "istio" {
  description = "Map of Istio application names"
  value = var.enable_istio ? {
    control_plane = module.istio[0].app_name
    beacon        = var.enable_mesh ? module.beacon[0].app_name : null
  } : null
}

output "ingress" {
  description = "Map of ingress application names"
  value = var.enable_istio ? {
    arr       = module.arr_ingress[0].app_name
    plex      = module.plex_ingress[0].app_name
    overseerr = module.overseerr_ingress[0].app_name
  } : null
}
