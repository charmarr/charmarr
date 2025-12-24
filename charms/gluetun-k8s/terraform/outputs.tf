output "app_name" {
  description = "Application name"
  value       = juju_application.gluetun.name
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
    vpn_gateway = "vpn-gateway"
  }
}
