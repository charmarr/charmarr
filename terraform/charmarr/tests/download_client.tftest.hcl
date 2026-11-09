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
  model           = { name = "charmarr" }
  vpn_provider    = "protonvpn"
  cluster_cidrs   = "10.1.0.0/16,10.152.183.0/24,10.0.0.0/8"
  storage_backend = "storage-class"
}

# --- download clients: every arr is wired to every download client ---

run "download_clients_wired_to_arrs" {
  command = plan

  variables {
    media_server = "jellyfin"
    enable_seerr = true
  }

  assert {
    condition     = length(juju_integration.download_client) == 4
    error_message = "Expected 2 download clients × 2 arrs = 4 download-client integrations"
  }

  assert {
    condition = alltrue([
      for key in ["qbittorrent_radarr", "qbittorrent_sonarr", "sabnzbd_radarr", "sabnzbd_sonarr"] :
      contains(keys(juju_integration.download_client), key)
    ])
    error_message = "Expected qbittorrent and sabnzbd to be integrated with both radarr and sonarr"
  }
}
