Feature: VPN Connection
  Test that gluetun establishes VPN and becomes active.

  Background:
    Given the gluetun-k8s charm is deployed with valid VPN config

  Scenario: VPN connects and charm becomes active
    Then the gluetun charm should be active
    And the gluetun charm status should show a VPN IP

  Scenario: Multimeter routes traffic through VPN
    Given the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to gluetun via vpn-gateway
    Then the multimeter external IP should match the gluetun VPN IP

  Scenario: Multimeter has VXLAN interface configured
    Given the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to gluetun via vpn-gateway
    Then the multimeter should have a vxlan interface
