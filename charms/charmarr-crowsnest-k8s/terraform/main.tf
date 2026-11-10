resource "juju_application" "crowsnest" {
  name       = var.app_name
  model_uuid = var.model_uuid
  trust      = true

  charm {
    name     = "charmarr-crowsnest-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = var.config
}
