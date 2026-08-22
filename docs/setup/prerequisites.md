# Prerequisites

## The Easy Way

Got a clean Ubuntu machine? Bootstrap everything with one command using [just](https://just.systems/).

Install just:

```bash
sudo snap install just --classic
```

Download the [justfile](https://github.com/charmarr/charmarr/blob/main/justfiles/charmarr-primitives.just) and run setup:

```bash
curl -O https://raw.githubusercontent.com/charmarr/charmarr/main/justfiles/charmarr-primitives.just
just -f charmarr-primitives.just setup
```

This installs Canonical K8s with local storage and an L2 load balancer pool, bootstraps Juju, and creates a `charmarr` model.

Verify it worked:

```bash
juju clouds    # should show ck8s
juju models    # should show charmarr model
```

To remove everything:

```bash
just -f charmarr-primitives.just nuke
```

---

## Manual Setup

Already have a cluster? Here's the shopping list.

| Category | Requirement | Status |
|----------|-------------|--------|
| Hardware | 8 GB RAM | Minimum |
| Hardware | 4 vCPUs | Minimum |
| OS | Ubuntu baremetal | Recommended |
| OS | Other Linux distros | Untested |
| OS | Virtualized setups | Untested |
| Kubernetes | Canonical K8s | Recommended |
| Kubernetes | MicroK8s | Supported |
| Kubernetes | Minikube | Supported |
| Kubernetes | Other standard K8s | Supported |
| Kubernetes | K3s / k3d | Supported |
| Kubernetes | LoadBalancer with 4+ IPs | Required |
| Kubernetes | Default StorageClass | Required |
| Tools | Juju 3.6.x | Required |

Charmarr deploys one ingress application per group of apps, so the cluster needs a LoadBalancer implementation that can hand out an address to each. Four covers the largest layout: one for the arrs, one for Seerr, and one each for Plex and Jellyfin.

### Canonical K8s

```bash
sudo snap install k8s --channel=1.32-classic/stable --classic
sudo k8s bootstrap
sudo k8s enable local-storage
sudo k8s set load-balancer.l2-mode=true load-balancer.cidrs="10.0.0.10-10.0.0.19"
sudo k8s enable load-balancer
sudo k8s status --wait-ready
```

Pick a `cidrs` range that is free on your LAN. This gives you the `csi-rawfile-default` StorageClass, which is `ReadWriteOnce` only, so deploy with `access_mode = "ReadWriteOnce"`.

### MicroK8s

```bash
sudo microk8s enable dns hostpath-storage metallb
```

The `hostpath-storage` addon provides `microk8s-hostpath`, which supports `ReadWriteMany`.

### Juju Setup

Install via snap:

```bash
sudo snap install juju --channel=3.6/stable
```

Juju `3.6.x` is also available from [nixpkgs](https://search.nixos.org/packages?query=juju) and as a [binary download](https://documentation.ubuntu.com/juju/3.6/howto/manage-juju/).

Bootstrap with your cluster:

```bash
# Add your k8s cluster to Juju (pipe kubeconfig into add-k8s)
sudo k8s config | juju add-k8s ck8s --client

# Bootstrap Juju on the cluster
juju bootstrap ck8s ck8s

# Create the charmarr model
juju add-model charmarr
```

See the Juju docs for [add-k8s](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/add-k8s/) and [bootstrap](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/bootstrap/).

---

## Ingress

Charmarr fronts every web UI with [Traefik](https://charmhub.io/traefik-k8s). It runs on any conformant cluster and needs nothing beyond a LoadBalancer address, so there is nothing to install and nothing to decide here.

If you want mutual TLS and zero-trust policies on internal traffic instead, Charmarr can run on Istio Ambient. That is a separate opt-in with its own prerequisites: see [Enabling Istio](../security/network.md#enabling-istio).

---

## Terraform

Required for Quick Deploy. Skip if using Manual Deploy.

Install from [HashiCorp's site](https://developer.hashicorp.com/terraform/install), or via snap:

```bash
sudo snap install terraform --classic
```

---

<div style="text-align: right" markdown>
[Quick Deploy :octicons-arrow-right-24:](quickdeploy.md)
</div>
