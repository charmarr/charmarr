data "juju_model" "model" {
  name = var.model
}

resource "juju_application" "qbittorrent" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "qbittorrent-k8s"
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
