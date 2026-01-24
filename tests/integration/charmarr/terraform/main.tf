variable "model" {
  type = string
}

variable "wireguard_private_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "enable_vpn" {
  type    = bool
  default = false
}

variable "enable_istio" {
  type    = bool
  default = false
}

variable "enable_mesh" {
  type    = bool
  default = false
}

module "charmarr" {
  source = "git::https://github.com/charmarr/charmarr//terraform/charmarr?ref=main"

  model = var.model

  storage_backend = "storage-class"
  storage_class   = "microk8s-hostpath"

  enable_vpn            = var.enable_vpn
  wireguard_private_key = var.wireguard_private_key
  vpn_provider          = "protonvpn"
  cluster_cidrs         = "10.1.0.0/16,10.152.183.0/24,10.0.0.0/8"

  enable_istio = var.enable_istio
  enable_mesh  = var.enable_mesh

  qbittorrent = {
    config = var.enable_vpn ? {} : { "unsafe-mode" = "true" }
  }

  sabnzbd = {
    config = var.enable_vpn ? {} : { "unsafe-mode" = "true" }
  }
}
