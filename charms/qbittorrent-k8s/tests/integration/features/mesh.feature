Feature: Service Mesh Integration
  Test that qbittorrent-k8s integrates correctly with Istio service mesh.

  Background:
    Given charmarr-storage is deployed
    And qbittorrent is deployed with storage relation
    And istio-k8s is deployed
    And istio-beacon is deployed
    And istio-ingress is deployed
    And qbittorrent is related to istio-beacon via service-mesh
    And qbittorrent is related to istio-ingress via istio-ingress-route

  Scenario: Charm remains active with mesh
    Then the qbittorrent charm should be active

  Scenario: WebUI accessible through mesh
    Given the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to qbittorrent via download-client
    And charmarr-multimeter is related to istio-beacon via service-mesh
    When credentials are retrieved from the qbittorrent secret
    Then the qbittorrent WebUI should authenticate successfully

  Scenario: WebUI accessible via ingress
    When credentials are retrieved from the qbittorrent secret
    Then the qbittorrent WebUI should be accessible via ingress
