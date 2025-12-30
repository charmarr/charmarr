Feature: Prowlarr FlareSolverr Integration
  Test that prowlarr-k8s integrates correctly with flaresolverr via service mesh.

  Background:
    Given istio-k8s is deployed
    And istio-beacon is deployed
    And prowlarr is deployed
    And prowlarr is related to istio-beacon via service-mesh
    And flaresolverr is deployed from charmhub
    And flaresolverr is related to istio-beacon via service-mesh
    And prowlarr is related to flaresolverr

  Scenario: Prowlarr has FlareSolverr proxy configured
    Then prowlarr should have a flaresolverr proxy configured
