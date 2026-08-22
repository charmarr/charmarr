terraform {
  required_version = ">= 1.5"

  required_providers {
    juju = {
      source  = "juju/juju"
      version = ">= 1.0, < 3.0"
    }
    # Only read when enable_istio = true. Terraform supplies an implicit empty
    # configuration, so traefik users need no kubeconfig and no provider block.
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.30"
    }
  }
}
