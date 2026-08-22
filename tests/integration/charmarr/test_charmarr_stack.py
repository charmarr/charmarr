# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr stack integration tests."""

from pytest_bdd import scenario

FEATURE = "features/charmarr-stack.feature"


@scenario(FEATURE, "Baseline deployment")
def test_baseline_deployment() -> None:
    """Baseline deployment without VPN, using the default traefik ingress."""


@scenario(FEATURE, "Deployment with VPN")
def test_deployment_with_vpn() -> None:
    """Deployment with VPN enabled."""


@scenario(FEATURE, "Deployment with VPN and Istio")
def test_deployment_with_vpn_and_istio() -> None:
    """Deployment with VPN and service mesh enabled."""
