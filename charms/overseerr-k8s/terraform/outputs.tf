output "app_name" {
  description = "Application name"
  value       = juju_application.overseerr.name
}

output "model" {
  description = "Juju model name"
  value       = data.juju_model.model.name
}

output "model_uuid" {
  description = "Juju model UUID"
  value       = data.juju_model.model.uuid
}

output "requires" {
  description = "Map of required endpoints for integration"
  value = {
    media_manager       = "media-manager"
    service_mesh        = "service-mesh"
    istio_ingress_route = "istio-ingress-route"
  }
}
