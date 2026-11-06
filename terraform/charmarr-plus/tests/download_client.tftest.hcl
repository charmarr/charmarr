mock_provider "juju" {
  mock_data "juju_model" {
    defaults = {
      uuid  = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
      name  = "charmarr-plus"
      owner = "admin"
    }
  }
}
mock_provider "kubernetes" {}
mock_provider "null" {}

variables {
  model           = { name = "charmarr-plus" }
  vpn_provider    = "protonvpn"
  cluster_cidrs   = "10.1.0.0/16,10.152.183.0/24,10.0.0.0/8"
  storage_backend = "storage-class"
}

# --- download clients: every arr instance is wired to every download client ---

run "download_clients_wired_to_arrs" {
  command = plan

  variables {
    media_server = "jellyfin"
    enable_seerr = true
  }

  assert {
    condition     = length(juju_integration.download_client) == 12
    error_message = "Expected 2 download clients × 6 arrs = 12 download-client integrations"
  }

  assert {
    condition = alltrue([
      for key in [
        "qbittorrent_radarr_hd", "qbittorrent_radarr_uhd", "qbittorrent_radarr_anime",
        "qbittorrent_sonarr_hd", "qbittorrent_sonarr_uhd", "qbittorrent_sonarr_anime",
        "sabnzbd_radarr_hd", "sabnzbd_radarr_uhd", "sabnzbd_radarr_anime",
        "sabnzbd_sonarr_hd", "sabnzbd_sonarr_uhd", "sabnzbd_sonarr_anime",
      ] :
      contains(keys(juju_integration.download_client), key)
    ])
    error_message = "Expected qbittorrent and sabnzbd to be integrated with every radarr/sonarr instance"
  }
}
