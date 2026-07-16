# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Charmarr stack integration tests."""

import pytest
from pytest_bdd import scenario

FEATURE = "features/charmarr-stack.feature"


@scenario(FEATURE, "Baseline deployment")
def test_baseline_deployment() -> None:
    """Baseline deployment without VPN or Istio."""


@scenario(FEATURE, "Deployment with VPN")
def test_deployment_with_vpn() -> None:
    """Deployment with VPN enabled."""


@pytest.mark.skip(reason="istio dev/edge regression; service mesh scenario hangs")
@scenario(FEATURE, "Deployment with VPN and Istio")
def test_deployment_with_vpn_and_istio() -> None:
    """Deployment with VPN and service mesh enabled."""
