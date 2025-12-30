data "juju_model" "model" {
  name = var.model
}

resource "juju_application" "prowlarr" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "prowlarr-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      log-level    = var.log_level
      ingress-path = var.ingress_path
    },
    var.config
  )
}
