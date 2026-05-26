# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

Feature: Seerr ingress integration
  As a Juju operator
  I want to expose seerr via ingress
  So that users can access seerr from outside the cluster

  Scenario: Seerr is accessible via ingress
    Given seerr is deployed
    And istio-k8s is deployed
    And istio-ingress is deployed
    And seerr is related to istio-ingress via istio-ingress-route
    Then seerr should be accessible via ingress
