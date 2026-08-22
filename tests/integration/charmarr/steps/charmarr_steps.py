# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Step definitions for charmarr module integration tests."""

import logging

import jubilant
from pytest_bdd import given, then
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from charmarr_lib.testing import TFManager

logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = ("connection is shut down", "connection refused")


def _is_transient_cli_error(exc: BaseException) -> bool:
    """Check if exception is a transient CLI error worth retrying.

    Workaround for https://github.com/canonical/jubilant/issues/241
    """
    if not isinstance(exc, jubilant.CLIError):
        return False
    stderr = (exc.stderr or "").lower()
    return any(err in stderr for err in TRANSIENT_ERRORS)


_retry_transient = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception(_is_transient_cli_error),
    before_sleep=lambda rs: logger.warning(
        f"Transient CLI error (attempt {rs.attempt_number}), retrying: {rs.outcome.exception()}"
    ),
)

@given("the charmarr module is deployed")
def deploy_baseline(tf_manager: TFManager, juju: jubilant.Juju, tf_env: dict) -> None:
    """Deploy charmarr baseline (no VPN, traefik ingress)."""
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
    """Swap traefik for istio-ingress and enable the mesh, on top of the VPN deployment."""
    logger.info("Deploying charmarr with VPN and Istio...")
    env = {**tf_env, "TF_VAR_enable_vpn": "true", "TF_VAR_enable_istio": "true"}
    tf_manager.apply(env)
    logger.info("Terraform apply complete, waiting for apps to settle...")
    wait_for_settled(juju)
    logger.info("Apps settled")


@_retry_transient
def _get_status(juju: jubilant.Juju) -> jubilant.Status:
    """Get juju status with retry on transient errors."""
    return juju.status()


@then("all apps should be active")
def all_apps_active(juju: jubilant.Juju) -> None:
    """Verify every app reached active."""
    status = _get_status(juju)
    for name, app in status.apps.items():
        assert app.app_status.current == "active", (
            f"{name} is {app.app_status.current}: {app.app_status.message}"
        )


@_retry_transient
def wait_for_settled(juju: jubilant.Juju) -> None:
    """Wait for apps to settle."""

    def apps_settled(status: jubilant.Status) -> bool:
        if not status.apps:
            logger.info("No apps deployed yet")
            return False
        for name, app in status.apps.items():
            if app.app_status.current != "active":
                logger.info(f"{name}: {app.app_status.current} (expected: active)")
                return False
        return True

    juju.wait(apps_settled, delay=10, successes=3, timeout=60 * 30)
