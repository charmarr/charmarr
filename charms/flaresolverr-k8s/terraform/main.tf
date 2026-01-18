data "juju_model" "model" {
  name = var.model
}

resource "juju_application" "flaresolverr" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid

  charm {
    name     = "flaresolverr-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      log-level = var.log_level
      timeout   = tostring(var.timeout)
    },
    var.config
  )
}
