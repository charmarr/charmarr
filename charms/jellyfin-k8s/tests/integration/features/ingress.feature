Feature: Jellyfin ingress integration
  As a Juju operator
  I want to expose jellyfin via ingress
  So that users can access jellyfin from outside the cluster

  Scenario: Jellyfin is accessible via ingress
    Given jellyfin is deployed
    And istio-k8s is deployed
    And istio-ingress is deployed
    And jellyfin is related to istio-ingress via istio-ingress-route
    Then jellyfin should be accessible via ingress
