output "app_name" {
  description = "Application name"
  value       = juju_application.charmarr_storage.name
}

output "model_uuid" {
  description = "Juju model UUID"
  value       = var.model_uuid
}

output "provides" {
  description = "Map of provided endpoints for integration"
  value = {
    media_storage     = "media-storage"
    provide_cmr_mesh  = "provide-cmr-mesh"
    crowsnest         = "crowsnest"
    metrics_endpoint  = "metrics-endpoint"
    grafana_dashboard = "grafana-dashboard"
  }
}

output "requires" {
  description = "Map of required endpoints for integration"
  value = {
    require_cmr_mesh = "require-cmr-mesh"
    service_mesh     = "service-mesh"
    logging          = "logging"
    charm_tracing    = "charm-tracing"
  }
}
