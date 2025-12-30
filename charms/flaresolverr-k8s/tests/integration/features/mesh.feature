Feature: FlareSolverr Service Mesh Integration
  Test that flaresolverr-k8s integrates correctly with Istio service mesh.

  Background:
    Given flaresolverr is deployed
    And istio-k8s is deployed
    And istio-beacon is deployed
    And flaresolverr is related to istio-beacon via service-mesh
    And the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to istio-beacon via service-mesh

  Scenario: Charm remains active with mesh
    Then the flaresolverr charm should be active

  Scenario: FlareSolverr service is accessible via mesh
    Then the flaresolverr health endpoint should respond
