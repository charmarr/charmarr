Feature: VPN Client Cleanup
  Test that VPN client resources are removed when relation is broken.

  Background:
    Given the gluetun-k8s charm is deployed with valid VPN config
    And the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to gluetun via vpn-gateway

  Scenario: Client containers are removed on relation broken
    When the vpn-gateway relation is removed
    Then the multimeter should not have gateway-init container
    And the multimeter should not have gateway-sidecar container

  Scenario: Client ConfigMap is removed on relation broken
    When the vpn-gateway relation is removed
    Then no gateway-client ConfigMap for multimeter should exist

  Scenario: Charm remains active after relation removed
    When the vpn-gateway relation is removed
    Then the gluetun charm should be active
    And the multimeter charm should be active
