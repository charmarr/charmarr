output "app_name" {
  description = "Application name"
  value       = juju_application.jellyfin.name
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
    provide_cmr_mesh     = "provide-cmr-mesh"
    crowsnest            = "crowsnest"
    media_server         = "media-server"
    velero_backup_config = "velero-backup-config"
    metrics_endpoint     = "metrics-endpoint"
    grafana_dashboard    = "grafana-dashboard"
  }
}

output "requires" {
  description = "Map of required endpoints for integration"
  value = {
    require_cmr_mesh    = "require-cmr-mesh"
    media_storage       = "media-storage"
    service_mesh        = "service-mesh"
    istio_ingress_route = "istio-ingress-route"
    ingress             = "ingress"
    logging             = "logging"
    charm_tracing       = "charm-tracing"
  }
}
