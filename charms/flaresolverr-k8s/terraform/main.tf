resource "juju_application" "flaresolverr" {
  name       = var.app_name
  model_uuid = var.model_uuid
  trust      = true

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
