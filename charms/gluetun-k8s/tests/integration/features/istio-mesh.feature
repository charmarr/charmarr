Feature: VPN through Istio Ambient Mesh
  Test that VPN routing works when client is in Istio service mesh.

  Background:
    Given istio-k8s is deployed
    And istio-beacon is deployed
    And the gluetun-k8s charm is deployed with valid VPN config
    And the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to istio-beacon via service-mesh
    And charmarr-multimeter is related to gluetun via vpn-gateway

  Scenario: Multimeter routes external traffic through VPN while in mesh
    Then the multimeter external IP should match the gluetun VPN IP

  Scenario: VXLAN interface works alongside ztunnel
    Then the multimeter should have a vxlan interface
