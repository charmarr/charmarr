data "juju_model" "model" {
  name  = var.model
  owner = var.owner
}

resource "juju_application" "radarr" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "radarr-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      variant          = var.variant
      trash-profiles   = var.trash_profiles
      log-level        = var.log_level
      ingress-port     = var.ingress_port
      ingress-path     = var.ingress_path
      timezone         = var.timezone
      api-key-rotation = var.api_key_rotation
    },
    var.config
  )
}
