Feature: Sonarr ingress integration
  As a Juju operator
  I want to expose sonarr via ingress
  So that users can access sonarr from outside the cluster

  Scenario: Sonarr is accessible via ingress
    Given sonarr is deployed
    And traefik is deployed
    And sonarr is related to traefik via ingress
    Then sonarr should be accessible via ingress
