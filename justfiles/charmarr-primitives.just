# Justfile for setting up charmarr infrastructure prerequisites (K8s + Juju)
#
# Usage:  just -f charmarr-primitives.just setup
#         just -f charmarr-primitives.just nuke

# Default recipe - list available recipes
default:
    @just --justfile {{justfile()}} --list

# Setup charmarr infrastructure (Canonical K8s + Juju)
setup:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "Installing Juju..."
    sudo snap install juju --channel=3.6/stable

    echo "Installing Canonical K8s (classic)..."
    sudo snap install k8s --channel=1.32-classic/stable --classic

    echo "Bootstrapping the cluster..."
    sudo k8s bootstrap
    sudo k8s status --wait-ready

    echo "Enabling storage and an L2 load balancer pool..."
    sudo k8s enable local-storage
    IPADDR=$(ip -4 -j route get 2.2.2.2 | jq -r '.[] | .prefsrc')
    IFS='.' read -r a b c d <<< "$IPADDR"
    sudo k8s set load-balancer.l2-mode=true load-balancer.cidrs="$IPADDR-$a.$b.$c.$((d + 9))"
    sudo k8s enable load-balancer

    echo "Waiting for the cluster to settle..."
    sudo k8s status --wait-ready

    echo "Exporting kubeconfig..."
    mkdir -p $HOME/.kube
    sudo k8s config > $HOME/.kube/config

    echo "Bootstrapping Juju..."
    juju add-k8s ck8s --client
    juju bootstrap ck8s ck8s

    echo "Creating charmarr model..."
    juju add-model --config logging-config="<root>=WARNING; unit=DEBUG" \
                   --config update-status-hook-interval="60m" charmarr

    echo ""
    echo "Charmarr infrastructure ready!"
    echo "  - Canonical K8s (classic) with Juju bootstrapped"
    echo "  - Default StorageClass: csi-rawfile-default (ReadWriteOnce)"
    echo "  - Model 'charmarr' created"
    echo ""
    echo "Verify with:"
    echo "  juju clouds"
    echo "  juju models"

# Nuke charmarr infrastructure
nuke:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Destroying Juju controller..."
    juju destroy-controller ck8s --destroy-all-models --destroy-storage --no-prompt || true
    echo "Removing snaps..."
    sudo snap remove --purge juju || true
    sudo snap remove --purge k8s || true
    echo "Cleaning up..."
    rm -rf ~/.local/share/juju ~/.cache/juju ~/.config/juju
    rm -f ~/.kube/config
    echo "Charmarr infrastructure nuked."
