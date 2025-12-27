Feature: Service Mesh Integration
  Test that sabnzbd-k8s integrates correctly with Istio service mesh.

  Background:
    Given charmarr-storage is deployed
    And sabnzbd is deployed with storage relation
    And istio-k8s is deployed
    And istio-beacon is deployed
    And istio-ingress is deployed
    And sabnzbd is related to istio-beacon via service-mesh
    And sabnzbd is related to istio-ingress via istio-ingress-route

  Scenario: Charm remains active with mesh
    Then the sabnzbd charm should be active

  Scenario: API accessible through mesh
    Given the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to sabnzbd via download-client
    And charmarr-multimeter is related to istio-beacon via service-mesh
    When the API key is retrieved from the sabnzbd secret
    Then the sabnzbd API should respond successfully

  Scenario: API accessible via ingress
    When the API key is retrieved from the sabnzbd secret
    Then the sabnzbd API should be accessible via ingress
