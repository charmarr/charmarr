variable "app_name" {
  description = "Name to give the deployed application"
  type        = string
  default     = "gluetun"
}

variable "channel" {
  description = "Channel that the charm is deployed from"
  type        = string
  default     = "latest/edge"
}

variable "config" {
  description = "Additional charm configuration options not covered by explicit variables"
  type        = map(string)
  default     = {}
}

variable "constraints" {
  description = "String listing constraints for this application"
  type        = string
  default     = "arch=amd64"
}

variable "model" {
  description = "Name of the model to deploy to"
  type        = string
}

variable "owner" {
  description = "Owner of the Juju model"
  type        = string
  default     = "admin"
}

variable "revision" {
  description = "Revision number of the charm"
  type        = number
  default     = null
}

variable "cluster_cidrs" {
  description = "Comma-separated pod/service CIDRs excluded from VPN routing"
  type        = string

  validation {
    condition     = length(var.cluster_cidrs) > 0
    error_message = "cluster_cidrs is required"
  }
}

variable "vpn_provider" {
  description = "VPN provider (nordvpn, mullvad, protonvpn, pia, surfshark, ivpn, windscribe, custom)"
  type        = string

  validation {
    condition     = length(var.vpn_provider) > 0
    error_message = "vpn_provider is required"
  }
}

variable "vpn_type" {
  description = "VPN protocol (wireguard only in v1)"
  type        = string
  default     = "wireguard"

  validation {
    condition     = var.vpn_type == "wireguard"
    error_message = "Only 'wireguard' is supported in v1"
  }
}

variable "wireguard_private_key_secret" {
  description = "Juju secret URI containing WireGuard private key (e.g., secret:vpn-key)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "wireguard_addresses" {
  description = "WireGuard interface address in CIDR format (required for mullvad, custom)"
  type        = string
  default     = ""
}

variable "server_countries" {
  description = "Comma-separated preferred server countries"
  type        = string
  default     = ""
}

variable "server_cities" {
  description = "Comma-separated preferred server cities"
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

variable "vxlan_id" {
  description = "VXLAN tunnel ID (1-16777215)"
  type        = number
  default     = 42

  validation {
    condition     = var.vxlan_id >= 1 && var.vxlan_id <= 16777215
    error_message = "vxlan_id must be between 1 and 16777215"
  }
}

variable "dns_over_tls" {
  description = "Enable DNS-over-TLS"
  type        = bool
  default     = false
}
