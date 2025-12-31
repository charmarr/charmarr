# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

Feature: Overseerr ingress integration
  As a Juju operator
  I want to expose overseerr via ingress
  So that users can access overseerr from outside the cluster

  Scenario: Overseerr is accessible via ingress
    Given overseerr is deployed
    And istio-k8s is deployed
    And istio-ingress is deployed
    And overseerr is related to istio-ingress via istio-ingress-route
    Then overseerr should be accessible via ingress
