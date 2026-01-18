data "juju_model" "model" {
  name = var.model
}

resource "juju_application" "charmarr_storage" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "charmarr-storage-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      backend-type      = var.backend_type
      storage-class     = var.storage_class
      size              = var.size
      nfs-server        = var.nfs_server
      nfs-path          = var.nfs_path
      hostpath          = var.hostpath
      access-mode       = var.access_mode
      puid              = tostring(var.puid)
      pgid              = tostring(var.pgid)
      cleanup-on-remove = tostring(var.cleanup_on_remove)
    },
    var.config
  )
}
