data "juju_model" "model" {
  name  = var.model
  owner = var.owner
}

resource "juju_application" "overseerr" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "overseerr-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      log-level = var.log_level
    },
    var.config
  )
}
