variable "model" {
  description = "Name of the Juju model to deploy to"
  type        = string
}

variable "owner" {
  description = "Owner of the Juju model"
  type        = string
  default     = "admin"
}

variable "channel" {
  description = "Default channel for Charmarr charms"
  type        = string
  default     = "latest/edge"
}

variable "traefik_channel" {
  description = "Channel for traefik-k8s, the default ingress provider (used when enable_istio = false)"
  type        = string
  default     = "latest/stable"
}

variable "istio_channel" {
  description = <<-EOT
    Channel for the Istio charms this module deploys (istio-ingress-k8s,
    istio-beacon-k8s). Set this to the same track as the istio-k8s control
    plane you deployed yourself; mismatched tracks are not supported.

    See https://github.com/canonical/service-mesh for the current release.
  EOT
  type        = string
  default     = "dev/edge"
}

variable "enable_istio" {
  description = <<-EOT
    Swap traefik-k8s for the Istio stack: istio-ingress-k8s for ingress plus
    istio-beacon-k8s enrolling every application in the ambient mesh.

    This module never installs the Istio control plane. Deploy an ambient
    control plane (e.g. the istio-k8s charm) yourself first. Setting this to
    true makes the plan probe the cluster for that control plane and fail if
    it is absent. Reading the cluster requires working kubeconfig credentials
    for the hashicorp/kubernetes provider; leaving this false requires none.
  EOT
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# VPN Configuration
# -----------------------------------------------------------------------------

variable "enable_vpn" {
  description = "Deploy Gluetun and integrate with download clients and indexer"
  type        = bool
  default     = true
}

variable "wireguard_private_key" {
  description = "WireGuard private key for VPN connection"
  type        = string
  sensitive   = true
  default     = ""
}

variable "vpn_provider" {
  description = "VPN provider (nordvpn, mullvad, protonvpn, pia, surfshark, ivpn, windscribe, custom)"
  type        = string
}

variable "cluster_cidrs" {
  description = "Comma-separated pod/service CIDRs excluded from VPN routing"
  type        = string
}

# -----------------------------------------------------------------------------
# Storage Configuration (Required)
# -----------------------------------------------------------------------------

variable "storage_backend" {
  description = "Storage backend type: storage-class, native-nfs, or hostpath"
  type        = string

  validation {
    condition     = contains(["storage-class", "native-nfs", "hostpath"], var.storage_backend)
    error_message = "storage_backend must be 'storage-class', 'native-nfs', or 'hostpath'"
  }
}

variable "storage_class" {
  description = "Kubernetes StorageClass name (required for storage_backend=storage-class)"
  type        = string
  default     = ""
}

variable "access_mode" {
  description = "PVC access mode: 'ReadWriteMany' or 'ReadWriteOnce'"
  type        = string
  default     = "ReadWriteMany"

  validation {
    condition     = contains(["ReadWriteMany", "ReadWriteOnce"], var.access_mode)
    error_message = "access_mode must be 'ReadWriteMany' or 'ReadWriteOnce'"
  }
}

variable "nfs_server" {
  description = "NFS server IP or hostname (required for storage_backend=native-nfs)"
  type        = string
  default     = ""
}

variable "nfs_path" {
  description = "NFS export path (required for storage_backend=native-nfs)"
  type        = string
  default     = ""
}

variable "hostpath" {
  description = "Host filesystem path (required for storage_backend=hostpath)"
  type        = string
  default     = ""
}

variable "storage_size" {
  description = "Storage size to provision (e.g., 100Gi, 1Ti)"
  type        = string
  default     = "100Gi"
}

# -----------------------------------------------------------------------------
# Optional VPN Configuration
# -----------------------------------------------------------------------------

variable "wireguard_addresses" {
  description = "WireGuard interface address in CIDR format (required for mullvad, custom)"
  type        = string
  default     = ""
}

variable "server_countries" {
  description = "Comma-separated preferred VPN server countries"
  type        = string
  default     = ""
}

variable "server_cities" {
  description = "Comma-separated preferred VPN server cities"
  type        = string
  default     = ""
}

variable "vpn_endpoint_ip" {
  description = "VPN server IP address (required for custom provider)"
  type        = string
  default     = ""
}

variable "vpn_endpoint_port" {
  description = "VPN server port (custom provider)"
  type        = number
  default     = 51820
}

variable "wireguard_public_key" {
  description = "Server's WireGuard public key (required for custom provider)"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Per-Application Overrides (Optional)
# -----------------------------------------------------------------------------

variable "storage" {
  description = "Override configuration for storage charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "gluetun" {
  description = "Override configuration for gluetun charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "qbittorrent" {
  description = "Override configuration for qbittorrent charm"
  type = object({
    constraints  = optional(string, "arch=amd64")
    revision     = optional(number, null)
    config       = optional(map(string), {})
    ingress_port = optional(number, 80)
    ingress_path = optional(string, "")
  })
  default = {}
}

variable "sabnzbd" {
  description = "Override configuration for sabnzbd charm"
  type = object({
    constraints  = optional(string, "arch=amd64")
    revision     = optional(number, null)
    config       = optional(map(string), {})
    ingress_port = optional(number, 80)
    ingress_path = optional(string, "")
  })
  default = {}
}

variable "prowlarr" {
  description = "Override configuration for prowlarr charm"
  type = object({
    constraints  = optional(string, "arch=amd64")
    revision     = optional(number, null)
    config       = optional(map(string), {})
    ingress_port = optional(number, 80)
    ingress_path = optional(string, "")
  })
  default = {}
}

variable "flaresolverr" {
  description = "Override configuration for flaresolverr charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "radarr" {
  description = "Override configuration for radarr charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_port   = optional(number, 80)
    ingress_path   = optional(string, "")
    trash_profiles = optional(string, "")
  })
  default = {}
}

variable "sonarr" {
  description = "Override configuration for sonarr charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_port   = optional(number, 80)
    ingress_path   = optional(string, "")
    trash_profiles = optional(string, "")
  })
  default = {}
}

# -----------------------------------------------------------------------------
# Media Server Selection
#
# Plex and Jellyfin are alternatives but not mutually exclusive, and both may be
# disabled if you only want the arrs. Each gets its own ingress because both are
# root-only, so they cannot share one under traefik's default path routing.
# -----------------------------------------------------------------------------

variable "media_server" {
  description = "Media server to deploy: 'plex', 'jellyfin', or 'none'"
  type        = string
  default     = "plex"

  validation {
    condition     = contains(["plex", "jellyfin", "none"], var.media_server)
    error_message = "media_server must be 'plex', 'jellyfin', or 'none'"
  }
}

variable "plex" {
  description = "Override configuration for plex charm (used when media_server = 'plex')"
  type = object({
    constraints          = optional(string, "arch=amd64")
    revision             = optional(number, null)
    config               = optional(map(string), {})
    claim_token          = optional(string, "")
    hardware_transcoding = optional(bool, false)
  })
  default = {}
}

variable "jellyfin" {
  description = "Override configuration for jellyfin charm (used when media_server = 'jellyfin')"
  type = object({
    constraints          = optional(string, "arch=amd64")
    revision             = optional(number, null)
    config               = optional(map(string), {})
    hardware_transcoding = optional(bool, false)
  })
  default = {}
}

variable "enable_overseerr" {
  description = <<-EOT
    Deploy Overseerr. Default true to keep in-place upgrades a no-op for
    existing deployments. Overseerr is deprecated; migrate to Seerr and
    set this to false. A future release will remove this flag and the
    overseerr module entirely.
  EOT
  type        = bool
  default     = true
}

variable "enable_seerr" {
  description = <<-EOT
    Deploy Seerr (successor to Overseerr). Default false for backward
    compatibility — new deployments should set this to true.

    Can run alongside Overseerr during migration. See
    docs/migration/overseerr-to-seerr.md.
  EOT
  type        = bool
  default     = false
}

variable "overseerr" {
  description = "Override configuration for overseerr charm (used when enable_overseerr = true)"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "seerr" {
  description = "Override configuration for seerr charm (used when enable_seerr = true)"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

# -----------------------------------------------------------------------------
# Observability (Optional)
# -----------------------------------------------------------------------------

variable "cos" {
  description = <<-EOT
    Wire the charmarr stack to a remote Canonical Observability Stack via
    cross-model relations. Set to null to skip the entire o11y plane
    (no otelcol, no crowsnest, no integrations). When non-null, deploys
    otelcol locally + crowsnest, and integrates them with the cos offers.

    Offer URLs are typically of the form `admin/cos.<offer-name>` and
    must already exist (run `juju offer` on the cos side first).
  EOT
  type = object({
    offers = object({
      grafana            = string
      loki_logging       = string
      mimir_remote_write = string
      send_ca_cert       = string
      tempo_tracing      = string
    })
  })
  default = null
}

variable "otelcol" {
  description = "Override configuration for the opentelemetry-collector-k8s charm (deployed when cos != null)"
  type = object({
    channel     = optional(string, "2/edge")
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "crowsnest" {
  description = "Override configuration for the charmarr-crowsnest-k8s charm (deployed when cos != null)"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

# -----------------------------------------------------------------------------
# Ingress and Mesh Charm Overrides (Optional)
#
# The ingress overrides apply to whichever provider is active, so revision and
# config must match the provider selected by enable_istio.
# -----------------------------------------------------------------------------

variable "beacon" {
  description = "Override configuration for istio-beacon charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "arr_ingress" {
  description = "Override configuration for arr-ingress charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "plex_ingress" {
  description = "Override configuration for plex-ingress charm (used when media_server = 'plex')"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "jellyfin_ingress" {
  description = "Override configuration for jellyfin-ingress charm (used when media_server = 'jellyfin')"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "seerr_ingress" {
  description = "Override configuration for seerr-ingress charm (used when enable_seerr = true)"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}
