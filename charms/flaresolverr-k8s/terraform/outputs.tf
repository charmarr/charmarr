output "app_name" {
  description = "Application name"
  value       = juju_application.flaresolverr.name
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
    flaresolverr     = "flaresolverr"
    provide_cmr_mesh = "provide-cmr-mesh"
  }
}

output "requires" {
  description = "Map of required endpoints for integration"
  value = {
    require_cmr_mesh = "require-cmr-mesh"
    service_mesh     = "service-mesh"
  }
}
