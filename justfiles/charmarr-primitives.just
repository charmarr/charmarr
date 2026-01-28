# Justfile for setting up charmarr infrastructure prerequisites (K8s + Juju)
#
# Usage:  just -f charmarr-primitives.just setup
#         just -f charmarr-primitives.just nuke

# Default recipe - list available recipes
default:
    @just --justfile {{justfile()}} --list

# Setup charmarr infrastructure (MicroK8s + Juju)
setup:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "Installing Juju..."
    sudo snap install juju --channel=3.6/stable

    echo "Installing MicroK8s (classic)..."
    sudo snap install microk8s --channel=1.32/stable --classic
    sudo usermod -a -G microk8s $USER

    echo "Waiting for MicroK8s to be ready..."
    sudo microk8s status --wait-ready

    echo "Enabling addons..."
    sudo microk8s enable dns
    sudo microk8s enable hostpath-storage
    IPADDR=$(ip -4 -j route get 2.2.2.2 | jq -r '.[] | .prefsrc')
    IFS='.' read -r a b c d <<< "$IPADDR"
    sudo microk8s enable metallb:$IPADDR-$a.$b.$c.$((d + 9))

    echo "Waiting for addons to be ready..."
    sudo microk8s kubectl rollout status deployment/coredns -n kube-system --timeout=300s
    sudo microk8s kubectl rollout status deployment/hostpath-provisioner -n kube-system --timeout=300s

    echo "Bootstrapping Juju..."
    sudo microk8s config | juju add-k8s mcrk8s --client
    juju bootstrap mcrk8s mcrk8s

    echo "Creating charmarr model..."
    juju add-model --config logging-config="<root>=WARNING; unit=DEBUG" \
                   --config update-status-hook-interval="60m" charmarr

    echo "Exporting kubeconfig..."
    mkdir -p $HOME/.kube
    sudo microk8s config > $HOME/.kube/config

    echo ""
    echo "Charmarr infrastructure ready!"
    echo "  - MicroK8s (classic) with Juju bootstrapped"
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
    juju destroy-controller mcrk8s --destroy-all-models --destroy-storage --no-prompt || true
    echo "Removing snaps..."
    sudo snap remove --purge juju || true
    sudo snap remove --purge microk8s || true
    echo "Cleaning up..."
    rm -rf ~/.local/share/juju ~/.cache/juju ~/.config/juju
    rm -f ~/.kube/config
    echo "Charmarr infrastructure nuked."
