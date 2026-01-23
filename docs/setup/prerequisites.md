# Prerequisites

## The Easy Way

Got a clean Ubuntu machine? Bootstrap everything with one command using [just](https://just.systems/).

Install just:

```bash
sudo snap install just
```

Download and run the [charmarr-primitives](https://github.com/adhityaravi/fire-flake/blob/main/fire-flake/justfiles/charmarr-primitives.just) recipe:

```bash
curl -O https://raw.githubusercontent.com/adhityaravi/fire-flake/main/fire-flake/justfiles/charmarr-primitives.just
just -f charmarr-primitives.just charmarr-primitives-setup
```

This installs and configures MicroK8s with all required addons, bootstraps Juju, and creates a `charmarr` model ready for deployment.

Verify it worked:

```bash
juju clouds    # should show mcrk8s
juju models    # should show charmarr model
```

To tear it all down later:

```bash
just -f charmarr-primitives.just charmarr-primitives-nuke
```

!!! warning
    The just recipe supports Canonical K8s via `k8s=ck8s`, but Charmarr doesn't support it yet — ck8s uses Cilium CNI by default.

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
| Kubernetes | MicroK8s | Recommended |
| Kubernetes | Other K8s with Calico | Supported |
| Kubernetes | Cilium CNI | Works with [tweaks](#cilium-cni) |
| Kubernetes | LB with 3+ IPs | Required |
| Tools | Juju 3.6.x | Required |

### MicroK8s Addons

```bash
sudo microk8s enable dns rbac hostpath-storage metrics-server metallb registry
```

### Juju Setup

Install:

```bash
sudo snap install juju --channel=3.6/stable
```

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

## Cilium CNI

If your cluster uses Cilium, you need to enable socket-level load balancing in host namespace only mode. This is required for Istio ambient mesh to function correctly.

**Helm:**

```yaml
socketLB:
  hostNamespaceOnly: true
```

**Cilium CLI:**

```bash
cilium config set bpf-lb-sock-hostns-only true
```

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
