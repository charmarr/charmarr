# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Pytest configuration for charmarr module integration tests."""

import logging
import os
from pathlib import Path
from typing import Generator

import jubilant
import pytest

from charmarr_lib.testing import TFManager

pytest_plugins = [
    "pytest_jubilant",
    "charmarr_lib.testing.steps.mesh",
    "tests.integration.charmarr.steps.charmarr_steps",
]

TERRAFORM_DIR = Path(__file__).parent / "terraform"
logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def tf_manager() -> Generator[TFManager, None, None]:
    """TFManager for the charmarr terraform module."""
    logger.info("Initializing TFManager...")
    manager = TFManager(TERRAFORM_DIR)
    logger.info("Running terraform init...")
    manager.init()
    logger.info("TFManager ready")
    yield manager


@pytest.fixture(scope="module")
def tf_env(juju: jubilant.Juju) -> dict:
    """Environment variables for terraform apply."""
    logger.info(f"Using juju model: {juju.model}")
    env = os.environ.copy()
    env["TF_VAR_model"] = juju.model
    if wg_key := os.environ.get("WIREGUARD_PRIVATE_KEY"):
        env["TF_VAR_wireguard_private_key"] = wg_key
    # enable_istio makes the module probe the cluster for an ambient control
    # plane, which needs credentials for the hashicorp/kubernetes provider.
    if "KUBE_CONFIG_PATH" not in env:
        kubeconfig = Path.home() / ".kube" / "config"
        if kubeconfig.is_file():
            env["KUBE_CONFIG_PATH"] = str(kubeconfig)
    return env
