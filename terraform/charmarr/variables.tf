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
  default     = "2/edge"
}

# -----------------------------------------------------------------------------
# VPN Configuration (Required)
# -----------------------------------------------------------------------------

variable "wireguard_private_key" {
  description = "WireGuard private key for VPN connection"
  type        = string
  sensitive   = true
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
    ingress_path = optional(string, "/qbittorrent")
  })
  default = {}
}

variable "sabnzbd" {
  description = "Override configuration for sabnzbd charm"
  type = object({
    constraints  = optional(string, "arch=amd64")
    revision     = optional(number, null)
    config       = optional(map(string), {})
    ingress_path = optional(string, "/sabnzbd")
  })
  default = {}
}

variable "prowlarr" {
  description = "Override configuration for prowlarr charm"
  type = object({
    constraints  = optional(string, "arch=amd64")
    revision     = optional(number, null)
    config       = optional(map(string), {})
    ingress_path = optional(string, "/prowlarr")
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

# -----------------------------------------------------------------------------
# Radarr Variants (HD, UHD, Anime)
# -----------------------------------------------------------------------------

variable "radarr_hd" {
  description = "Override configuration for radarr-hd charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_path   = optional(string, "/radarr-hd")
    trash_profiles = optional(string, "hd-bluray-web")
  })
  default = {}
}

variable "radarr_uhd" {
  description = "Override configuration for radarr-uhd charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_path   = optional(string, "/radarr-uhd")
    trash_profiles = optional(string, "")
  })
  default = {}
}

variable "radarr_anime" {
  description = "Override configuration for radarr-anime charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_path   = optional(string, "/radarr-anime")
    trash_profiles = optional(string, "")
  })
  default = {}
}

# -----------------------------------------------------------------------------
# Sonarr Variants (HD, UHD, Anime)
# -----------------------------------------------------------------------------

variable "sonarr_hd" {
  description = "Override configuration for sonarr-hd charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_path   = optional(string, "/sonarr-hd")
    trash_profiles = optional(string, "web-1080p")
  })
  default = {}
}

variable "sonarr_uhd" {
  description = "Override configuration for sonarr-uhd charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_path   = optional(string, "/sonarr-uhd")
    trash_profiles = optional(string, "")
  })
  default = {}
}

variable "sonarr_anime" {
  description = "Override configuration for sonarr-anime charm"
  type = object({
    constraints    = optional(string, "arch=amd64")
    revision       = optional(number, null)
    config         = optional(map(string), {})
    ingress_path   = optional(string, "/sonarr-anime")
    trash_profiles = optional(string, "")
  })
  default = {}
}

# -----------------------------------------------------------------------------
# Media Server & Request Management
# -----------------------------------------------------------------------------

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

variable "overseerr" {
  description = "Override configuration for overseerr charm"
  type = object({
    constraints = optional(string, "arch=amd64")
    revision    = optional(number, null)
    config      = optional(map(string), {})
  })
  default = {}
}
