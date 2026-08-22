# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "juju_model" "model" {
  name  = var.model
  owner = var.owner
}

# Istio is never deployed by this module — the operator installs the control
# plane themselves. These two data sources are a guard: they fail the plan if
# enable_istio is set but the cluster has no ambient control plane to attach to.
#
# The probe is two hops because kubernetes_resources errors outright on a kind
# the API server does not know. CustomResourceDefinition is always registered,
# so hop 1 safely establishes whether GatewayClass exists before hop 2 reads it.
# The signal itself is the istio-waypoint GatewayClass: cluster-scoped (so no
# guessing which namespace istiod landed in), only created by a running istiod,
# and ambient-only.
data "kubernetes_resources" "crds" {
  count       = var.enable_istio ? 1 : 0
  api_version = "apiextensions.k8s.io/v1"
  kind        = "CustomResourceDefinition"

  lifecycle {
    postcondition {
      condition = contains(
        [for o in self.objects : o.metadata.name],
        "gatewayclasses.gateway.networking.k8s.io"
      )
      error_message = "enable_istio = true but the Gateway API CRDs are not installed. Deploy an Istio ambient control plane (e.g. the istio-k8s charm) first, or set enable_istio = false to use traefik."
    }
  }
}

locals {
  enable_plex     = var.media_server == "plex"
  enable_jellyfin = var.media_server == "jellyfin"

  gateway_api = var.enable_istio ? contains(
    [for o in data.kubernetes_resources.crds[0].objects : o.metadata.name],
    "gatewayclasses.gateway.networking.k8s.io"
  ) : false
}

data "kubernetes_resources" "gateway_classes" {
  count       = local.gateway_api ? 1 : 0
  api_version = "gateway.networking.k8s.io/v1"
  kind        = "GatewayClass"

  lifecycle {
    postcondition {
      condition = contains(
        [for o in self.objects : o.metadata.name],
        "istio-waypoint"
      )
      error_message = "enable_istio = true but no Istio ambient control plane was found (the istio-waypoint GatewayClass is missing). Deploy an Istio ambient control plane first, or set enable_istio = false to use traefik."
    }
  }
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

# HACK: Workaround for Juju Terraform provider config drift. The provider's Read phase
# picks up CLI-set config into state, then Update unsets any config not in the plan.
# We use CLI because setting secrets directly in TF is blocked by juju/juju#20143.
# The always_run trigger ensures we re-apply the config after every apply.
resource "null_resource" "gluetun_secret_config" {
  count = var.enable_vpn ? 1 : 0

  triggers = {
    always_run = timestamp()
  }

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
  access_mode       = var.access_mode
  nfs_server        = var.nfs_server
  nfs_path          = var.nfs_path
  hostpath          = var.hostpath
  size              = var.storage_size
  cleanup_on_remove = true
}

module "gluetun" {
  count  = var.enable_vpn ? 1 : 0
  source = "git::https://github.com/charmarr/charmarr//charms/gluetun-k8s/terraform?ref=main"

  model               = var.model
  owner               = var.owner
  app_name            = "gluetun"
  channel             = var.channel
  constraints         = var.gluetun.constraints
  revision            = var.gluetun.revision
  config              = var.gluetun.config
  cluster_cidrs       = var.cluster_cidrs
  vpn_provider        = var.vpn_provider
  wireguard_addresses = var.wireguard_addresses
  # FIXME: Uncomment once https://github.com/juju/juju/issues/20143 is fixed
  # wireguard_private_key_secret = ""
  server_countries     = var.server_countries
  server_cities        = var.server_cities
  vpn_endpoint_ip      = var.vpn_endpoint_ip
  vpn_endpoint_port    = var.vpn_endpoint_port
  wireguard_public_key = var.wireguard_public_key
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
  ingress_port        = var.qbittorrent.ingress_port
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
  ingress_port        = var.sabnzbd.ingress_port
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
  ingress_port     = var.prowlarr.ingress_port
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

module "radarr" {
  source = "git::https://github.com/charmarr/charmarr//charms/radarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "radarr"
  channel          = var.channel
  constraints      = var.radarr.constraints
  revision         = var.radarr.revision
  config           = var.radarr.config
  ingress_port     = var.radarr.ingress_port
  ingress_path     = var.radarr.ingress_path
  api_key_rotation = "monthly"
}

module "sonarr" {
  source = "git::https://github.com/charmarr/charmarr//charms/sonarr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "sonarr"
  channel          = var.channel
  constraints      = var.sonarr.constraints
  revision         = var.sonarr.revision
  config           = var.sonarr.config
  ingress_port     = var.sonarr.ingress_port
  ingress_path     = var.sonarr.ingress_path
  api_key_rotation = "monthly"
}

module "plex" {
  count  = local.enable_plex ? 1 : 0
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

module "jellyfin" {
  count  = local.enable_jellyfin ? 1 : 0
  source = "git::https://github.com/charmarr/charmarr//charms/jellyfin-k8s/terraform?ref=main"

  model                = var.model
  owner                = var.owner
  app_name             = "jellyfin"
  channel              = var.channel
  constraints          = var.jellyfin.constraints
  revision             = var.jellyfin.revision
  config               = var.jellyfin.config
  hardware_transcoding = var.jellyfin.hardware_transcoding
}

module "overseerr" {
  count  = var.enable_overseerr ? 1 : 0
  source = "git::https://github.com/charmarr/charmarr//charms/overseerr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "overseerr"
  channel          = var.channel
  constraints      = var.overseerr.constraints
  revision         = var.overseerr.revision
  config           = var.overseerr.config
  api_key_rotation = "monthly"
}

module "seerr" {
  count  = var.enable_seerr ? 1 : 0
  source = "git::https://github.com/charmarr/charmarr//charms/seerr-k8s/terraform?ref=main"

  model            = var.model
  owner            = var.owner
  app_name         = "seerr"
  channel          = var.channel
  constraints      = var.seerr.constraints
  revision         = var.seerr.revision
  config           = var.seerr.config
  api_key_rotation = "monthly"
}

# -----------------------------------------------------------------------------
# Observability Charms (deployed when var.cos != null)
# -----------------------------------------------------------------------------

resource "juju_application" "otelcol" {
  count      = var.cos != null ? 1 : 0
  name       = "otelcol"
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "opentelemetry-collector-k8s"
    channel  = var.otelcol.channel
    revision = var.otelcol.revision
  }

  constraints = var.otelcol.constraints
  config      = var.otelcol.config
}

module "crowsnest" {
  count  = var.cos != null ? 1 : 0
  source = "git::https://github.com/charmarr/charmarr//charms/charmarr-crowsnest-k8s/terraform?ref=main"

  model       = var.model
  owner       = var.owner
  app_name    = "crowsnest"
  channel     = var.channel
  constraints = var.crowsnest.constraints
  revision    = var.crowsnest.revision
  config      = var.crowsnest.config
}

data "juju_offer" "cos_grafana" {
  count = var.cos != null ? 1 : 0
  url   = var.cos.offers.grafana
}

data "juju_offer" "cos_loki_logging" {
  count = var.cos != null ? 1 : 0
  url   = var.cos.offers.loki_logging
}

data "juju_offer" "cos_mimir_remote_write" {
  count = var.cos != null ? 1 : 0
  url   = var.cos.offers.mimir_remote_write
}

data "juju_offer" "cos_send_ca_cert" {
  count = var.cos != null ? 1 : 0
  url   = var.cos.offers.send_ca_cert
}

data "juju_offer" "cos_tempo_tracing" {
  count = var.cos != null ? 1 : 0
  url   = var.cos.offers.tempo_tracing
}

# -----------------------------------------------------------------------------
# Ingress Charms
#
# Terraform does not allow a dynamic module source, so each ingress instance is
# a pair of mutually exclusive module blocks. local.*_ingress_app in
# integrations.tf collapses the pair back to a single application name.
# -----------------------------------------------------------------------------

module "beacon" {
  count  = var.enable_istio ? 1 : 0
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

module "arr_ingress_traefik" {
  count  = var.enable_istio ? 0 : 1
  source = "git::https://github.com/canonical/traefik-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "arr-ingress"
  channel     = var.traefik_channel
  constraints = var.arr_ingress.constraints
  revision    = var.arr_ingress.revision
  config      = var.arr_ingress.config
}

module "plex_ingress" {
  count  = var.enable_istio && local.enable_plex ? 1 : 0
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "plex-ingress"
  channel     = var.istio_channel
  constraints = var.plex_ingress.constraints
  revision    = var.plex_ingress.revision
  config      = var.plex_ingress.config
}

module "plex_ingress_traefik" {
  count  = !var.enable_istio && local.enable_plex ? 1 : 0
  source = "git::https://github.com/canonical/traefik-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "plex-ingress"
  channel     = var.traefik_channel
  constraints = var.plex_ingress.constraints
  revision    = var.plex_ingress.revision
  config      = var.plex_ingress.config
}

module "jellyfin_ingress" {
  count  = var.enable_istio && local.enable_jellyfin ? 1 : 0
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "jellyfin-ingress"
  channel     = var.istio_channel
  constraints = var.jellyfin_ingress.constraints
  revision    = var.jellyfin_ingress.revision
  config      = var.jellyfin_ingress.config
}

module "jellyfin_ingress_traefik" {
  count  = !var.enable_istio && local.enable_jellyfin ? 1 : 0
  source = "git::https://github.com/canonical/traefik-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "jellyfin-ingress"
  channel     = var.traefik_channel
  constraints = var.jellyfin_ingress.constraints
  revision    = var.jellyfin_ingress.revision
  config      = var.jellyfin_ingress.config
}

module "seerr_ingress" {
  count  = var.enable_istio && var.enable_seerr ? 1 : 0
  source = "git::https://github.com/canonical/istio-ingress-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "seerr-ingress"
  channel     = var.istio_channel
  constraints = var.seerr_ingress.constraints
  revision    = var.seerr_ingress.revision
  config      = var.seerr_ingress.config
}

module "seerr_ingress_traefik" {
  count  = !var.enable_istio && var.enable_seerr ? 1 : 0
  source = "git::https://github.com/canonical/traefik-k8s-operator//terraform?ref=main"

  model_uuid  = data.juju_model.model.uuid
  app_name    = "seerr-ingress"
  channel     = var.traefik_channel
  constraints = var.seerr_ingress.constraints
  revision    = var.seerr_ingress.revision
  config      = var.seerr_ingress.config
}
