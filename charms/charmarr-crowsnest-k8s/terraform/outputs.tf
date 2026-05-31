output "app_name" {
  description = "Application name"
  value       = juju_application.crowsnest.name
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
    provide_cmr_mesh  = "provide-cmr-mesh"
    metrics_endpoint  = "metrics-endpoint"
    grafana_dashboard = "grafana-dashboard"
    grafana_source    = "grafana-source"
    sloth             = "sloth"
  }
}

output "requires" {
  description = "Map of required endpoints for integration"
  value = {
    require_cmr_mesh    = "require-cmr-mesh"
    crowsnest           = "crowsnest"
    service_mesh        = "service-mesh"
    logging             = "logging"
    charm_tracing       = "charm-tracing"
    istio_ingress_route = "istio-ingress-route"
  }
}
