# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Istio mesh step definitions for gluetun-k8s integration tests."""

import jubilant
from pytest_bdd import given

from charmarr_lib.testing import wait_for_active_idle

ISTIO_CHANNEL = "2/edge"


@given("istio-k8s is deployed")
def deploy_istio(juju: jubilant.Juju) -> None:
    """Deploy istio-k8s from Charmhub."""
    status = juju.status()
    if "istio-k8s" in status.apps:
        return
    juju.deploy("istio-k8s", app="istio-k8s", channel=ISTIO_CHANNEL, trust=True)
    wait_for_active_idle(juju)


@given("istio-beacon-k8s is deployed")
def deploy_istio_beacon(juju: jubilant.Juju) -> None:
    """Deploy istio-beacon-k8s from Charmhub."""
    status = juju.status()
    if "istio-beacon" in status.apps:
        return
    juju.deploy("istio-beacon-k8s", app="istio-beacon", channel=ISTIO_CHANNEL, trust=True)
    wait_for_active_idle(juju)


@given("charmarr-multimeter is related to istio-beacon via service-mesh")
def relate_multimeter_istio(juju: jubilant.Juju) -> None:
    """Integrate multimeter with istio-beacon via service-mesh relation."""
    status = juju.status()
    app = status.apps.get("charmarr-multimeter")
    if app and "service-mesh" in app.relations:
        return
    juju.integrate("charmarr-multimeter:service-mesh", "istio-beacon:service-mesh")
    wait_for_active_idle(juju)
