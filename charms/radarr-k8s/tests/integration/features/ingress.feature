Feature: Radarr ingress integration
  As a Juju operator
  I want to expose radarr via ingress
  So that users can access radarr from outside the cluster

  Scenario: Radarr is accessible via ingress
    Given radarr is deployed
    And istio-k8s is deployed
    And istio-ingress is deployed
    And radarr is related to istio-ingress via istio-ingress-route
    Then radarr should be accessible via ingress
