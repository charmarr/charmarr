# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Test runner for VPN through Istio mesh feature."""

from pytest_bdd import scenarios

scenarios("../features/istio-mesh.feature")
