data "juju_model" "model" {
  name = var.model
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
      log-level      = var.log_level
      ingress-path   = var.ingress_path
      trash-profiles = var.trash_profiles
      is-4k          = var.is_4k
    },
    var.config
  )
}
