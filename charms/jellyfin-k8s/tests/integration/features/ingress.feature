Feature: Jellyfin ingress integration
  As a Juju operator
  I want to expose jellyfin via ingress
  So that users can access jellyfin from outside the cluster

  Scenario: Jellyfin is accessible via ingress
    Given jellyfin is deployed
    And traefik is deployed
    And jellyfin is related to traefik via ingress
    Then jellyfin should be accessible via ingress
