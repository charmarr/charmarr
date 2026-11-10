resource "juju_application" "overseerr" {
  name       = var.app_name
  model_uuid = var.model_uuid
  trust      = true

  charm {
    name     = "overseerr-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      ingress-port     = var.ingress_port
      log-level        = var.log_level
      api-key-rotation = var.api_key_rotation
    },
    var.config
  )
}
