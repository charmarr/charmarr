output "app_name" {
  description = "Application name"
  value       = juju_application.radarr.name
}

output "model" {
  description = "Juju model name"
  value       = data.juju_model.model.name
}

output "model_uuid" {
  description = "Juju model UUID"
  value       = data.juju_model.model.uuid
}

output "provides" {
  description = "Map of provided endpoints for integration"
  value = {
    media_manager = "media-manager"
  }
}

output "requires" {
  description = "Map of required endpoints for integration"
  value = {
    media_indexer        = "media-indexer"
    download_client      = "download-client"
    media_storage        = "media-storage"
    vpn_gateway          = "vpn-gateway"
    service_mesh         = "service-mesh"
    velero_backup_config = "velero-backup-config"
    istio_ingress_route  = "istio-ingress-route"
  }
}
