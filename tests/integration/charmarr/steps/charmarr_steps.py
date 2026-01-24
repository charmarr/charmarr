# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for charmarr module integration tests."""

import logging

import jubilant
from pytest_bdd import given, then

from charmarr_lib.testing import TFManager

logger = logging.getLogger(__name__)

WAITING_APPS = {"plex", "overseerr"}


@given("the charmarr module is deployed")
def deploy_baseline(tf_manager: TFManager, juju: jubilant.Juju, tf_env: dict) -> None:
    """Deploy charmarr baseline (no VPN, no Istio)."""
    logger.info("Deploying charmarr baseline...")
    tf_manager.apply(tf_env)
    logger.info("Terraform apply complete, waiting for apps to settle...")
    wait_for_settled(juju)
    logger.info("Apps settled")


@given("the charmarr module is deployed with VPN")
def deploy_with_vpn(tf_manager: TFManager, juju: jubilant.Juju, tf_env: dict) -> None:
    """Deploy charmarr with VPN enabled."""
    logger.info("Deploying charmarr with VPN...")
    env = {**tf_env, "TF_VAR_enable_vpn": "true"}
    tf_manager.apply(env)
    logger.info("Terraform apply complete, waiting for apps to settle...")
    wait_for_settled(juju)
    logger.info("Apps settled")


@given("the charmarr module is deployed with VPN and Istio")
def deploy_with_vpn_istio(tf_manager: TFManager, juju: jubilant.Juju, tf_env: dict) -> None:
    """Deploy charmarr with VPN and Istio enabled."""
    logger.info("Deploying charmarr with VPN and Istio...")
    env = {**tf_env, "TF_VAR_enable_vpn": "true", "TF_VAR_enable_istio": "true", "TF_VAR_enable_mesh": "true"}
    tf_manager.apply(env)
    logger.info("Terraform apply complete, waiting for apps to settle...")
    wait_for_settled(juju)
    logger.info("Apps settled")


@then("all apps except plex and overseerr should be active")
def all_apps_active(juju: jubilant.Juju) -> None:
    """Verify all apps except plex and overseerr are active."""
    status = juju.status()
    for name, app in status.apps.items():
        if name in WAITING_APPS:
            continue
        assert app.app_status.current == "active", (
            f"{name} is {app.app_status.current}: {app.app_status.message}"
        )


@then("plex and overseerr should be waiting")
def plex_overseerr_waiting(juju: jubilant.Juju) -> None:
    """Verify plex and overseerr are in waiting status."""
    status = juju.status()
    for name in WAITING_APPS:
        app = status.apps.get(name)
        if not app:
            continue
        assert app.app_status.current == "waiting", (
            f"{name} is {app.app_status.current}: {app.app_status.message}"
        )


def wait_for_settled(juju: jubilant.Juju) -> None:
    """Wait for apps to settle."""

    def apps_settled(status: jubilant.Status) -> bool:
        if not status.apps:
            logger.info("No apps deployed yet")
            return False
        for name, app in status.apps.items():
            current = app.app_status.current
            if name in WAITING_APPS:
                if current != "waiting":
                    logger.info(f"{name}: {current} (expected: waiting)")
                    return False
            elif current != "active":
                logger.info(f"{name}: {current} (expected: active)")
                return False
        return True

    juju.wait(apps_settled, delay=10, successes=3, timeout=60 * 30)
