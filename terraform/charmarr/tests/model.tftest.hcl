mock_provider "juju" {
  mock_resource "juju_model" {
    defaults = {
      uuid = "12345678-1234-1234-1234-123456789abc"
    }
  }

  mock_data "juju_model" {
    defaults = {
      uuid  = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
      name  = "charmarr"
      owner = "admin"
    }
  }
}
mock_provider "kubernetes" {}
mock_provider "null" {}

variables {
  vpn_provider    = "protonvpn"
  cluster_cidrs   = "10.1.0.0/16,10.152.183.0/24,10.0.0.0/8"
  storage_backend = "storage-class"
}

# --- model: create when no uuid provided ---

run "model_created_when_no_uuid" {
  command = plan

  assert {
    condition     = length(juju_model.charmarr) == 1
    error_message = "Expected juju_model.charmarr to be created when no UUID is provided"
  }

  assert {
    condition     = length(data.juju_model.charmarr) == 0
    error_message = "Expected no data source lookup when creating a model"
  }

  assert {
    condition     = juju_model.charmarr[0].name == "charmarr"
    error_message = "Expected default model name to be 'charmarr'"
  }
}

# --- model: all inputs are passed through to juju_model ---

run "model_created_with_full_inputs" {
  command = plan

  variables {
    model = {
      name = "my-charmarr"
      cloud = {
        name   = "microk8s"
        region = "localhost"
      }
      annotations = {
        owner = "charmarr"
        env   = "test"
      }
      config            = { logging-config = "<root>=INFO" }
      constraints       = "arch=amd64 mem=4G"
      credential        = "my-credential"
      target_controller = "my-controller"
    }
  }

  assert {
    condition     = length(juju_model.charmarr) == 1
    error_message = "Expected juju_model.charmarr to be created when no UUID is provided"
  }

  assert {
    condition     = length(data.juju_model.charmarr) == 0
    error_message = "Expected no data source lookup when creating a model"
  }

  assert {
    condition     = juju_model.charmarr[0].cloud[0].name == "microk8s"
    error_message = "Expected cloud name to be passed through as 'microk8s'"
  }

  assert {
    condition     = juju_model.charmarr[0].cloud[0].region == "localhost"
    error_message = "Expected cloud region to be passed through as 'localhost'"
  }
}

# --- model: attach to existing model by UUID ---

run "model_attached_when_uuid_provided" {
  command = plan

  variables {
    model = { uuid = "12345678-1234-1234-1234-123456789abc" }
  }

  assert {
    condition     = length(juju_model.charmarr) == 0
    error_message = "Expected no juju_model resource to be created when UUID is provided"
  }

  assert {
    condition     = length(data.juju_model.charmarr) == 1
    error_message = "Expected data source lookup when UUID is provided"
  }

  assert {
    condition     = data.juju_model.charmarr[0].uuid == "12345678-1234-1234-1234-123456789abc"
    error_message = "Expected data source to look up the provided UUID"
  }
}

# --- validation: invalid UUID is rejected ---

run "model_invalid_uuid_rejected" {
  command = plan

  variables {
    model = { uuid = "not-a-uuid" }
  }

  expect_failures = [var.model]
}

# --- validation: create-only fields cannot be combined with uuid ---

run "model_uuid_with_cloud_rejected" {
  command = plan

  variables {
    model = {
      uuid  = "12345678-1234-1234-1234-123456789abc"
      cloud = { name = "microk8s" }
    }
  }

  expect_failures = [var.model]
}

run "model_uuid_with_constraints_rejected" {
  command = plan

  variables {
    model = {
      uuid        = "12345678-1234-1234-1234-123456789abc"
      constraints = "arch=amd64"
    }
  }

  expect_failures = [var.model]
}

run "model_uuid_with_annotations_rejected" {
  command = plan

  variables {
    model = {
      uuid        = "12345678-1234-1234-1234-123456789abc"
      annotations = { owner = "charmarr" }
    }
  }

  expect_failures = [var.model]
}

# --- validation: empty name when creating is rejected ---

run "model_empty_name_when_creating_rejected" {
  command = plan

  variables {
    model = { name = "" }
  }

  expect_failures = [var.model]
}
