# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "juju_model" "model" {
  name  = var.model
  owner = var.owner
}

# -----------------------------------------------------------------------------
# Juju Secret for WireGuard Private Key
# -----------------------------------------------------------------------------

resource "juju_secret" "wireguard_key" {
  count      = var.enable_vpn ? 1 : 0
  model_uuid = data.juju_model.model.uuid
  name       = "vpn-key"

  value = {
    private-key = var.wireguard_private_key
  }
}

resource "juju_access_secret" "gluetun_wireguard_access" {
  count      = var.enable_vpn ? 1 : 0
  model_uuid = data.juju_model.model.uuid
  secret_id  = juju_secret.wireguard_key[0].secret_id

  applications = [module.gluetun[0].app_name]

  depends_on = [module.gluetun]
}

# HACK: Workaround for Juju secret race condition. The charm needs secret access
# granted before the secret config is set, but Terraform can't express this ordering
# through juju_application config. We deploy gluetun without the secret, grant access,
# then set the config via CLI.
resource "null_resource" "gluetun_secret_config" {
  count = var.enable_vpn ? 1 : 0

  depends_on = [
    module.gluetun,
    juju_access_secret.gluetun_wireguard_access
  ]

  provisioner "local-exec" {
    command = "juju config gluetun wireguard-private-key-secret=secret:${juju_secret.wireguard_key[0].secret_id} -m ${var.model}"
  }
}

# -----------------------------------------------------------------------------
# Charmarr Charms
# -----------------------------------------------------------------------------

module "storage" {
  source = "git::https://github.com/charmarr/charmarr//charms/charmarr-storage-k8s/terraform?ref=main"

  model             = var.model
  owner             = var.owner
  app_name          = "storage"
  channel           = var.channel
  constraints       = var.storage.constraints
  revision          = var.storage.revision
  config            = var.storage.config
  backend_type      = var.storage_backend
  storage_class     = var.storage_class
  nfs_server        = var.nfs_server
  nfs_path          = var.nfs_path
  hostpath          = var.hostpath
  size              = var.storage_size
  cleanup_on_remove = true
}

module "gluetun" {
  count  = var.enable_vpn ? 1 : 0
  source = "git::https://github.com/charmarr/charmarr//charms/gluetun-k8s/terraform?ref=main"

  model                        = var.model
  owner                        = var.owner
  app_name                     = "gluetun"
  channel                      = var.channel
  constraints                  = var.gluetun.constraints
  revision                     = var.gluetun.revision
  config                       = var.gluetun.config
  cluster_cidrs       = var.cluster_cidrs
  vpn_provider        = var.vpn_provider
  wireguard_addresses = var.wireguard_addresses
  # FIXME: Uncomment once https://github.com/juju/juju/issues/20143 is fixed
  # wireguard_private_key_secret = ""
  server_countries             = var.server_countries
  server_cities                = var.server_cities
  vpn_endpoint_ip              = var.vpn_endpoint_ip
  vpn_endpoint_port            = var.vpn_endpoint_port
  wireguard_public_key         = var.wireguard_public_key
}

module "qbittorrent" {
  source = "git::https://github.com/charmarr/charmarr//charms/qbittorrent-k8s/terraform?ref=main"

  model               = var.model
  owner               = var.owner
  app_name            = "qbittorrent"
  channel             = var.channel
  constraints         = var.qbittorrent.constraints
  revision            = var.qbittorrent.revision
  config              = var.qbittorrent.config
  ingress_path        = var.qbittorrent.ingress_path
  credential_rotation = "monthly"
}

module "sabnzbd" {
  source = "git::https://github.com/charmarr/charmarr//charms/sabnzbd-k8s/terraform?ref=main"

  model               = var.model
  owner               = var.owner
  app_name            = "sabnzbd"
  channel             = var.channel
  constraints         = var.sabnzbd.constraints
  revision            = var.sabnzbd.revision
  config              = var.sabnzbd.config
  ingress_path        = var.sabnzbd.ingress_path
  credential_rotation = "monthly"
}

module "prowlarr" {
  source = "git::https://github.com/charmarr/charmarr//charms/prowlarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "prowlarr"
  channel          = var.channel
  constraints      = var.prowlarr.constraints
  revision         = var.prowlarr.revision
  config           = var.prowlarr.config
  ingress_path     = var.prowlarr.ingress_path
  api_key_rotation = "monthly"
}

module "flaresolverr" {
  source = "git::https://github.com/charmarr/charmarr//charms/flaresolverr-k8s/terraform?ref=main"

  model       = var.model
  owner       = var.owner
  app_name    = "flaresolverr"
  channel     = var.channel
  constraints = var.flaresolverr.constraints
  revision    = var.flaresolverr.revision
  config      = var.flaresolverr.config
}

# -----------------------------------------------------------------------------
# Radarr Variants
# -----------------------------------------------------------------------------

module "radarr_hd" {
  source = "git::https://github.com/charmarr/charmarr//charms/radarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "radarr-hd"
  channel          = var.channel
  constraints      = var.radarr_hd.constraints
  revision         = var.radarr_hd.revision
  config           = var.radarr_hd.config
  variant          = "standard"
  ingress_path     = var.radarr_hd.ingress_path
  trash_profiles   = var.radarr_hd.trash_profiles
  api_key_rotation = "monthly"
}

module "radarr_uhd" {
  source = "git::https://github.com/charmarr/charmarr//charms/radarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "radarr-uhd"
  channel          = var.channel
  constraints      = var.radarr_uhd.constraints
  revision         = var.radarr_uhd.revision
  config           = var.radarr_uhd.config
  variant          = "4k"
  ingress_path     = var.radarr_uhd.ingress_path
  trash_profiles   = var.radarr_uhd.trash_profiles
  api_key_rotation = "monthly"
}

module "radarr_anime" {
  source = "git::https://github.com/charmarr/charmarr//charms/radarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "radarr-anime"
  channel          = var.channel
  constraints      = var.radarr_anime.constraints
  revision         = var.radarr_anime.revision
  config           = var.radarr_anime.config
  variant          = "anime"
  ingress_path     = var.radarr_anime.ingress_path
  trash_profiles   = var.radarr_anime.trash_profiles
  api_key_rotation = "monthly"
}

# -----------------------------------------------------------------------------
# Sonarr Variants
# -----------------------------------------------------------------------------

module "sonarr_hd" {
  source = "git::https://github.com/charmarr/charmarr//charms/sonarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "sonarr-hd"
  channel          = var.channel
  constraints      = var.sonarr_hd.constraints
  revision         = var.sonarr_hd.revision
  config           = var.sonarr_hd.config
  variant          = "standard"
  ingress_path     = var.sonarr_hd.ingress_path
  trash_profiles   = var.sonarr_hd.trash_profiles
  api_key_rotation = "monthly"
}

module "sonarr_uhd" {
  source = "git::https://github.com/charmarr/charmarr//charms/sonarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "sonarr-uhd"
  channel          = var.channel
  constraints      = var.sonarr_uhd.constraints
  revision         = var.sonarr_uhd.revision
  config           = var.sonarr_uhd.config
  variant          = "4k"
  ingress_path     = var.sonarr_uhd.ingress_path
  trash_profiles   = var.sonarr_uhd.trash_profiles
  api_key_rotation = "monthly"
}

module "sonarr_anime" {
  source = "git::https://github.com/charmarr/charmarr//charms/sonarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "sonarr-anime"
  channel          = var.channel
  constraints      = var.sonarr_anime.constraints
  revision         = var.sonarr_anime.revision
  config           = var.sonarr_anime.config
  variant          = "anime"
  ingress_path     = var.sonarr_anime.ingress_path
  trash_profiles   = var.sonarr_anime.trash_profiles
  api_key_rotation = "monthly"
}

# -----------------------------------------------------------------------------
# Media Server & Request Management
# -----------------------------------------------------------------------------

module "plex" {
  source = "git::https://github.com/charmarr/charmarr//charms/plex-k8s/terraform?ref=main"

  model                = var.model
  owner                = var.owner
  app_name             = "plex"
  channel              = var.channel
  constraints          = var.plex.constraints
  revision             = var.plex.revision
  config               = var.plex.config
  claim_token          = var.plex.claim_token
  hardware_transcoding = var.plex.hardware_transcoding
}

module "overseerr" {
  source = "git::https://github.com/charmarr/charmarr//charms/overseerr-k8s/terraform?ref=main"

  model       = var.model
  owner       = var.owner
  app_name    = "overseerr"
  channel     = var.channel
  constraints = var.overseerr.constraints
  revision    = var.overseerr.revision
  config      = var.overseerr.config
}

# -----------------------------------------------------------------------------
# Istio Charms
# -----------------------------------------------------------------------------

module "istio" {
  count  = var.enable_istio ? 1 : 0
  source = "git::https://github.com/canonical/istio-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "istio"
  channel     = var.istio_channel
  constraints = var.istio.constraints
  revision    = var.istio.revision
  config      = var.istio.config
}

module "beacon" {
  count  = var.enable_mesh ? 1 : 0
  source = "git::https://github.com/canonical/istio-beacon-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "beacon"
  channel     = var.istio_channel
  constraints = var.beacon.constraints
  revision    = var.beacon.revision
  config      = var.beacon.config
}

module "arr_ingress" {
  count  = var.enable_istio ? 1 : 0
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "arr-ingress"
  channel     = var.istio_channel
  constraints = var.arr_ingress.constraints
  revision    = var.arr_ingress.revision
  config      = var.arr_ingress.config
}

module "plex_ingress" {
  count  = var.enable_istio ? 1 : 0
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "plex-ingress"
  channel     = var.istio_channel
  constraints = var.plex_ingress.constraints
  revision    = var.plex_ingress.revision
  config      = var.plex_ingress.config
}

module "overseerr_ingress" {
  count  = var.enable_istio ? 1 : 0
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "overseerr-ingress"
  channel     = var.istio_channel
  constraints = var.overseerr_ingress.constraints
  revision    = var.overseerr_ingress.revision
  config      = var.overseerr_ingress.config
}
