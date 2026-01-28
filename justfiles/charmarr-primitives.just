# Justfile for setting up charmarr infrastructure prerequisites (K8s + Juju)
# Uses concierge for a minimal MicroK8s + Juju setup
#
# Usage:  just -f charmarr-primitives.just setup
#         just -f charmarr-primitives.just nuke

config_url := "https://raw.githubusercontent.com/charmarr/charmarr/main/justfiles/concierge.yaml"

# Default recipe - list available recipes
default:
    @just --justfile {{justfile()}} --list

# Setup charmarr infrastructure (MicroK8s + Juju)
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Installing concierge..."
    sudo snap install concierge --classic

    echo "Downloading concierge config..."
    curl -sO {{config_url}}

    echo "Running concierge prepare..."
    sudo concierge prepare

    echo "Creating charmarr model..."
    juju add-model charmarr

    echo "Exporting kubeconfig..."
    mkdir -p $HOME/.kube
    sudo microk8s config > $HOME/.kube/config

    echo ""
    echo "Charmarr infrastructure ready!"
    echo "  - MicroK8s bootstrapped with Juju"
    echo "  - Model 'charmarr' created"
    echo ""
    echo "Verify with:"
    echo "  juju clouds"
    echo "  juju models"

# Nuke charmarr infrastructure
nuke:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Restoring system with concierge..."
    sudo concierge restore || true
    sudo snap remove --purge concierge || true
    rm -rf ~/.local/share/juju ~/.cache/juju ~/.config/juju
    rm -f ~/.kube/config
    rm -f concierge.yaml
    echo "Charmarr infrastructure nuked."
