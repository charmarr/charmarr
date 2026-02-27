data "juju_model" "model" {
  name  = var.model
  owner = var.owner
}

resource "juju_application" "plex" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "plex-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      claim-token          = var.claim_token
      hardware-transcoding = tostring(var.hardware_transcoding)
      ingress-port         = var.ingress_port
      timezone             = var.timezone
    },
    var.config
  )
}
