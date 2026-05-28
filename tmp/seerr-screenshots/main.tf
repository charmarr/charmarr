# Dummy deployment for taking fresh Seerr screenshots.
# Disposable — delete the whole tmp/ dir after screenshots are captured.
#
# Usage:
#   cd tmp/seerr-screenshots
#   tofu init
#   tofu apply -auto-approve
#
# After apply:
#   1. Grab a Plex claim token from https://plex.tv/claim
#   2. juju config plex claim-token="claim-XXXXX" -m seerr-screenshots
#   3. Wait for plex to go active: juju status -m seerr-screenshots
#   4. Get the seerr-ingress LoadBalancer IP from `juju status`
#   5. Open http://<seerr-ingress-ip> in a browser and walk the wizard
#
# Teardown:
#   tofu destroy -auto-approve
#   juju destroy-model seerr-screenshots --no-prompt --force --destroy-storage

terraform {
  required_version = ">= 1.5"
  required_providers {
    juju = {
      source  = "juju/juju"
      version = ">= 1.0, < 1.4"
    }
  }
}

module "charmarr" {
  source = "../../terraform/charmarr"

  model = "seerr-screenshots"

  # Storage — single-node hostpath, no NFS gymnastics
  storage_backend = "hostpath"
  hostpath        = "/tmp/seerr-screenshots-storage"

  # VPN off — screenshots don't need anonymized traffic, and skipping
  # WireGuard removes one moving part. Unsafe-mode is set on the download
  # clients so they're allowed to start without VPN protection.
  enable_vpn    = false
  vpn_provider  = "protonvpn" # required variable even when enable_vpn=false
  cluster_cidrs = "10.1.0.0/16,10.152.183.0/24,192.168.0.0/24"

  qbittorrent = {
    config = {
      "unsafe-mode" = "true"
    }
  }
  sabnzbd = {
    config = {
      "unsafe-mode" = "true"
    }
  }

  # Istio ingress only (no mesh — screenshots don't need authz policies)
  enable_istio = true
  enable_mesh  = false

  # The whole point: seerr only, no overseerr
  enable_overseerr = false
  enable_seerr     = true
}

output "ingress" {
  value = module.charmarr.ingress
}

output "applications" {
  value = module.charmarr.applications
}
