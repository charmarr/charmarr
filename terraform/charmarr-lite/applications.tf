# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "juju_model" "model" {
  name = var.model
}

# -----------------------------------------------------------------------------
# Juju Secret for WireGuard Private Key
# -----------------------------------------------------------------------------

resource "juju_secret" "wireguard_key" {
  model = var.model
  name  = "wireguard-private-key"

  value = {
    key = var.wireguard_private_key
  }
}

resource "juju_access_secret" "gluetun_wireguard_access" {
  model = var.model
  name  = juju_secret.wireguard_key.name

  applications = [module.gluetun.app_name]

  depends_on = [module.gluetun]
}

# -----------------------------------------------------------------------------
# Charmarr Charms
# -----------------------------------------------------------------------------

module "storage" {
  source = "git::https://github.com/charmarr/charmarr//charms/charmarr-storage-k8s/terraform?ref=main"

  model         = var.model
  app_name      = "storage"
  channel       = var.channel
  constraints   = var.storage.constraints
  revision      = var.storage.revision
  config        = var.storage.config
  backend_type  = var.storage_backend
  storage_class = var.storage_class
  nfs_server    = var.nfs_server
  nfs_path      = var.nfs_path
  hostpath      = var.hostpath
  size          = var.storage_size
}

module "gluetun" {
  source = "git::https://github.com/charmarr/charmarr//charms/gluetun-k8s/terraform?ref=main"

  model                        = var.model
  app_name                     = "gluetun"
  channel                      = var.channel
  constraints                  = var.gluetun.constraints
  revision                     = var.gluetun.revision
  config                       = var.gluetun.config
  cluster_cidrs                = var.cluster_cidrs
  vpn_provider                 = var.vpn_provider
  wireguard_private_key_secret = juju_secret.wireguard_key.secret_id
  wireguard_addresses          = var.wireguard_addresses
  server_countries             = var.server_countries
  server_cities                = var.server_cities
  vpn_endpoint_ip              = var.vpn_endpoint_ip
  vpn_endpoint_port            = var.vpn_endpoint_port
  wireguard_public_key         = var.wireguard_public_key
}

module "qbittorrent" {
  source = "git::https://github.com/charmarr/charmarr//charms/qbittorrent-k8s/terraform?ref=main"

  model               = var.model
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
  app_name    = "flaresolverr"
  channel     = var.channel
  constraints = var.flaresolverr.constraints
  revision    = var.flaresolverr.revision
  config      = var.flaresolverr.config
}

module "radarr" {
  source = "git::https://github.com/charmarr/charmarr//charms/radarr-k8s/terraform?ref=main"

  model            = var.model
  app_name         = "radarr"
  channel          = var.channel
  constraints      = var.radarr.constraints
  revision         = var.radarr.revision
  config           = var.radarr.config
  ingress_path     = var.radarr.ingress_path
  api_key_rotation = "monthly"
}

module "sonarr" {
  source = "git::https://github.com/charmarr/charmarr//charms/sonarr-k8s/terraform?ref=main"

  model            = var.model
  app_name         = "sonarr"
  channel          = var.channel
  constraints      = var.sonarr.constraints
  revision         = var.sonarr.revision
  config           = var.sonarr.config
  ingress_path     = var.sonarr.ingress_path
  api_key_rotation = "monthly"
}

module "plex" {
  source = "git::https://github.com/charmarr/charmarr//charms/plex-k8s/terraform?ref=main"

  model                = var.model
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
  source = "git::https://github.com/canonical/istio-k8s-operator//terraform?ref=main"

  model    = var.model
  app_name = "istio"
  channel  = var.istio_channel
}

module "arr_ingress" {
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model    = var.model
  app_name = "arr-ingress"
  channel  = var.istio_channel
}

module "plex_ingress" {
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model    = var.model
  app_name = "plex-ingress"
  channel  = var.istio_channel
}

module "overseerr_ingress" {
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model    = var.model
  app_name = "overseerr-ingress"
  channel  = var.istio_channel
}
