mock_provider "juju" {
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
  model           = "charmarr"
  vpn_provider    = "protonvpn"
  cluster_cidrs   = "10.1.0.0/16,10.152.183.0/24,10.0.0.0/8"
  storage_backend = "storage-class"
}

# --- ingress: disabling managed ingress leaves the endpoints free ---

run "ingress_disabled_skips_managed_ingress" {
  command = plan

  variables {
    enable_ingress = false
    media_server   = "jellyfin"
    enable_seerr   = true
  }

  assert {
    condition     = length(module.arr_ingress) == 0 && length(module.arr_ingress_traefik) == 0
    error_message = "Expected no managed arr ingress modules when enable_ingress = false"
  }

  assert {
    condition     = length(module.jellyfin_ingress) == 0 && length(module.jellyfin_ingress_traefik) == 0
    error_message = "Expected no managed jellyfin ingress modules when enable_ingress = false"
  }

  assert {
    condition     = length(module.seerr_ingress) == 0 && length(module.seerr_ingress_traefik) == 0
    error_message = "Expected no managed seerr ingress modules when enable_ingress = false"
  }

  assert {
    condition     = length(juju_integration.arr_ingress) == 0
    error_message = "Expected no arr ingress integrations when enable_ingress = false"
  }

  assert {
    condition     = length(juju_integration.jellyfin_ingress_jellyfin) == 0
    error_message = "Expected no jellyfin ingress integration when enable_ingress = false"
  }

  assert {
    condition     = length(juju_integration.seerr_ingress_seerr) == 0
    error_message = "Expected no seerr ingress integration when enable_ingress = false"
  }

  assert {
    condition     = output.ingress.provider == "external" && output.ingress.enabled == false
    error_message = "Expected the ingress output to report external mode when enable_ingress = false"
  }
}
