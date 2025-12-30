Feature: Prowlarr ingress integration
  As a Juju operator
  I want to expose prowlarr via ingress
  So that users can access prowlarr from outside the cluster

  Scenario: Prowlarr is accessible via ingress
    Given prowlarr is deployed
    And istio-k8s is deployed
    And istio-ingress is deployed
    And prowlarr is related to istio-ingress via istio-ingress-route
    Then prowlarr should be accessible via ingress
