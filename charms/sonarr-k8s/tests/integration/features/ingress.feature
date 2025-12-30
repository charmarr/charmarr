Feature: Sonarr ingress integration
  As a Juju operator
  I want to expose sonarr via ingress
  So that users can access sonarr from outside the cluster

  Scenario: Sonarr is accessible via ingress
    Given sonarr is deployed
    And istio-k8s is deployed
    And istio-ingress is deployed
    And sonarr is related to istio-ingress via istio-ingress-route
    Then sonarr should be accessible via ingress
