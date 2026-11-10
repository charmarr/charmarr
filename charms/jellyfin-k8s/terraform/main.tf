resource "juju_application" "jellyfin" {
  name       = var.app_name
  model_uuid = var.model_uuid
  trust      = true

  charm {
    name     = "jellyfin-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      hardware-transcoding = tostring(var.hardware_transcoding)
      ingress-port         = var.ingress_port
      timezone             = var.timezone
    },
    var.config
  )
}
