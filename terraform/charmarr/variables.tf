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

variable "istio_channel" {
  description = "Channel for Istio charms (istio-k8s, istio-ingress-k8s, istio-beacon-k8s)"
  type        = string
  default     = "dev/edge"
}

variable "enable_istio" {
  description = "Enable Istio for ingress"
  type        = bool
  default     = false
}

variable "enable_mesh" {
  description = "Enable service mesh hardening (requires enable_istio = true)"
  type        = bool
  default     = false

  validation {
    condition     = var.enable_mesh == false || var.enable_istio == true
    error_message = "enable_mesh = true requires enable_istio = true"
  }
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

variable "plex" {
  description = "Override configuration for plex charm"
  type = object({
    constraints          = optional(string, "arch=amd64")
    revision             = optional(number, null)
    config               = optional(map(string), {})
    claim_token          = optional(string, "")
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
# Istio Charm Overrides (Optional)
# -----------------------------------------------------------------------------

variable "istio" {
  description = "Override configuration for istio charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

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
  description = "Override configuration for plex-ingress charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "overseerr_ingress" {
  description = "Override configuration for overseerr-ingress charm (used when enable_overseerr = true and enable_istio = true)"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}

variable "seerr_ingress" {
  description = "Override configuration for seerr-ingress charm (used when enable_seerr = true and enable_istio = true)"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}
