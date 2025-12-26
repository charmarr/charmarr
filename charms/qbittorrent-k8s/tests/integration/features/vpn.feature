Feature: VPN Integration
  Test that qbittorrent-k8s integrates correctly with gluetun VPN gateway.

  Background:
    Given charmarr-storage is deployed
    And the charmarr-multimeter charm is deployed
    And gluetun is deployed with valid VPN config
    And qbittorrent is deployed with storage relation
    And qbittorrent is related to gluetun via vpn-gateway

  Scenario: Charm becomes active with VPN
    Then the qbittorrent charm should be active
    And the gluetun charm should be active

  Scenario: StatefulSet has VPN sidecar containers
    Then the qbittorrent StatefulSet should have init container "vpn-route-init"
    And the qbittorrent StatefulSet should have container "vpn-route-sidecar"
