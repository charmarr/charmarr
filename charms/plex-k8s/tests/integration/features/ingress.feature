Feature: Plex ingress integration
  As a Juju operator
  I want to expose plex via ingress
  So that users can access plex from outside the cluster

  Scenario: Plex is accessible via ingress
    Given plex is deployed
    And istio-k8s is deployed
    And istio-ingress is deployed
    And plex is related to istio-ingress via istio-ingress-route
    Then plex should be accessible via ingress
