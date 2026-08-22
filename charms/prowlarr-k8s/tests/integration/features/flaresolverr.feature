Feature: Prowlarr FlareSolverr Integration
  Test that prowlarr-k8s integrates correctly with flaresolverr.

  Background:
    Given prowlarr is deployed
    And flaresolverr is deployed from charmhub
    And prowlarr is related to flaresolverr

  Scenario: Prowlarr has FlareSolverr proxy configured
    Then prowlarr should have a flaresolverr proxy configured
