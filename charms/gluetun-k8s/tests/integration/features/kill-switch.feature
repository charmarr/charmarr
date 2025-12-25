Feature: VPN Kill Switch
  Test NetworkPolicy kill switch protects client traffic.

  Background:
    Given the gluetun-k8s charm is deployed with valid VPN config
    And the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to gluetun via vpn-gateway

  Scenario: Kill switch NetworkPolicy is created
    Then a NetworkPolicy for multimeter should exist
    And the NetworkPolicy should allow traffic only to gateway and cluster CIDRs

  Scenario: Kill switch blocks external traffic when VPN is down
    When the gluetun container is stopped
    Then the multimeter should not be able to reach external IPs

  Scenario: Kill switch NetworkPolicy is removed on relation removal
    When the vpn-gateway relation is removed
    Then no NetworkPolicy for multimeter should exist
