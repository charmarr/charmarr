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

This uses [concierge](https://github.com/canonical/concierge) to install MicroK8s with required addons, bootstrap Juju, and create a `charmarr` model.

Verify it worked:

```bash
juju clouds    # should show microk8s
juju models    # should show charmarr model
```

To remove everything:

```bash
just -f charmarr-primitives.just nuke
```

---

## Manual Setup

Already have a cluster? Here's the shopping list.

| Category | Requirement | Status | Istio Support |
|----------|-------------|--------|---------------|
| Hardware | 8 GB RAM | Minimum | - |
| Hardware | 4 vCPUs | Minimum | - |
| OS | Ubuntu baremetal | Recommended | - |
| OS | Other Linux distros | Untested | - |
| OS | Virtualized setups | Untested | - |
| Kubernetes | MicroK8s | Recommended | Yes |
| Kubernetes | Minikube | Supported | Yes |
| Kubernetes | Other standard K8s | Supported | Yes |
| Kubernetes | K3s / k3d | Supported | [Needs tweaks](#compatibility-checklist) |
| Kubernetes | Cilium CNI | Supported | [Needs tweaks](#compatibility-checklist) |
| Kubernetes | LB with 3+ IPs | - | Required |
| Tools | Juju 3.6.x | Required | Required |

### MicroK8s Addons

```bash
sudo microk8s enable dns hostpath-storage metallb
```

### Juju Setup

Install via snap:

```bash
sudo snap install juju --channel=3.6/stable
```

Juju `3.6.x` is also available from [nixpkgs](https://search.nixos.org/packages?query=juju) and as a [binary download](https://documentation.ubuntu.com/juju/3.6/howto/manage-juju/).

Bootstrap with your cluster:

```bash
# Add your k8s cluster to Juju (pipe kubeconfig into add-k8s)
sudo microk8s config | juju add-k8s mcrk8s --client

# Bootstrap Juju on the cluster
juju bootstrap mcrk8s mcrk8s

# Create the charmarr model
juju add-model charmarr
```

See the Juju docs for [add-k8s](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/add-k8s/) and [bootstrap](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/bootstrap/).

---

## Ingress & Security

Charmarr lets you opt-in to [Istio Ambient](https://istio.io/latest/docs/ambient/overview/) for ingress and service mesh security. Enabling both is **strongly recommended** if your cluster is compatible as it greatly simplifies ingress setup and provides cluster internal network security between services.

### Compatibility Checklist

- [x] Used [The Easy Way](#the-easy-way) to setup the cluster

**— OR —**

- [x] No Istiod already running on the cluster (if you don't know, it's probably not)
- [x] Not using K3s or k3d (read the warning below)
- [x] Not using Cilium CNI (or willing to [configure it](https://istio.io/latest/docs/ambient/install/platform-prerequisites/#cilium))

All checked? Enable Istio and mesh while deploying.

Not all checked? Disable Istio and handle ingress yourself. See [Istio platform prerequisites](https://istio.io/latest/docs/ambient/install/platform-prerequisites/) for details.

!!! warning
    K3s and k3d use non-standard CNI paths that can conflict with Istio Ambient. Adding Istio may disrupt the CNI chain and cause hard-to-debug networking issues. It can work with careful configuration: [K3s docs](https://istio.io/latest/docs/ambient/install/platform-prerequisites/#k3s), [k3d docs](https://istio.io/latest/docs/ambient/install/platform-prerequisites/#k3d). So if you want to use it with Istio Ambient, do it at your own discretion.

---

## OpenTofu

Required for Quick Deploy. Skip if using Manual Deploy.

Install from [opentofu.org](https://opentofu.org/docs/intro/install/), or via snap:

```bash
sudo snap install opentofu --classic
```

---

<div style="text-align: right" markdown>
[Quick Deploy :octicons-arrow-right-24:](quickdeploy.md)
</div>
