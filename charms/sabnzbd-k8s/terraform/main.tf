data "juju_model" "model" {
  name = var.model
}

resource "juju_application" "sabnzbd" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "sabnzbd-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      log-level           = var.log_level
      ingress-path        = var.ingress_path
      timezone            = var.timezone
      credential-rotation = var.credential_rotation
    },
    var.config
  )
}
