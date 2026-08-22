Feature: Charmarr Stack Deployment
  Test the charmarr terraform module deploys a functional media stack.

  Scenario: Baseline deployment
    Given the charmarr module is deployed
    Then all apps should be active

  Scenario: Deployment with VPN
    Given the charmarr module is deployed with VPN
    Then all apps should be active

  Scenario: Deployment with VPN and Istio
    Given istio-k8s is deployed
    And the charmarr module is deployed with VPN and Istio
    Then all apps should be active
