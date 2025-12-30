data "juju_model" "model" {
  name = var.model
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
      timezone             = var.timezone
    },
    var.config
  )
}
