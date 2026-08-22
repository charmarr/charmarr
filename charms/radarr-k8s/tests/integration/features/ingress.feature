Feature: Radarr ingress integration
  As a Juju operator
  I want to expose radarr via ingress
  So that users can access radarr from outside the cluster

  Scenario: Radarr is accessible via ingress
    Given radarr is deployed
    And traefik is deployed
    And radarr is related to traefik via ingress
    Then radarr should be accessible via ingress
