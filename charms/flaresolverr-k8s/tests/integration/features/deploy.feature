Feature: FlareSolverr Deployment
  Test that flaresolverr-k8s deploys correctly.

  Background:
    Given flaresolverr is deployed

  Scenario: Charm becomes active
    Then the flaresolverr charm should be active
