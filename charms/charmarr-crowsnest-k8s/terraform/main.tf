data "juju_model" "model" {
  name  = var.model
  owner = var.owner
}

resource "juju_application" "crowsnest" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "charmarr-crowsnest-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = var.config
}
