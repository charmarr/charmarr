Feature: VPN Integration
  Test that sabnzbd-k8s integrates correctly with gluetun VPN gateway.

  Background:
    Given charmarr-storage is deployed
    And the charmarr-multimeter charm is deployed
    And gluetun is deployed with valid VPN config
    And sabnzbd is deployed with storage relation
    And sabnzbd is related to gluetun via vpn-gateway

  Scenario: Charm becomes active with VPN
    Then the sabnzbd charm should be active
    And the gluetun charm should be active

  Scenario: StatefulSet has VPN sidecar containers
    Then the sabnzbd StatefulSet should have init container "vpn-route-init"
    And the sabnzbd StatefulSet should have container "vpn-route-sidecar"
