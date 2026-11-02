# -----------------------------------------------------------------------------
# Model Management
#
# Either creates the model this module deploys into (juju_model resource) or
# looks up an existing one by UUID (juju_model data source). Which branch runs
# is driven purely by whether var.model.uuid is set.
# -----------------------------------------------------------------------------

locals {
  create_model = var.model.uuid == null
  model_uuid   = local.create_model ? juju_model.charmarr[0].uuid : data.juju_model.charmarr[0].uuid
  model_name   = local.create_model ? juju_model.charmarr[0].name : data.juju_model.charmarr[0].name
  # When targeting an existing model, resolve its real owner so the charm
  # modules can look it up by name even when it is not owned by var.owner.
  model_owner = local.create_model ? var.owner : data.juju_model.charmarr[0].owner
}

resource "juju_model" "charmarr" {
  count = local.create_model ? 1 : 0

  name = var.model.name

  dynamic "cloud" {
    for_each = var.model.cloud != null ? [var.model.cloud] : []
    content {
      name   = cloud.value.name
      region = cloud.value.region
    }
  }

  annotations       = var.model.annotations
  config            = var.model.config
  constraints       = var.model.constraints
  credential        = var.model.credential
  target_controller = var.model.target_controller
}

data "juju_model" "charmarr" {
  count = local.create_model ? 0 : 1

  uuid = var.model.uuid
}