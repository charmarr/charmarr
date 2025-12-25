Feature: VXLAN ID Propagation
  Test that VXLAN ID config changes propagate to client containers.

  Background:
    Given the gluetun-k8s charm is deployed with valid VPN config
    And the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to gluetun via vpn-gateway

  Scenario: Default VXLAN ID is used in client containers
    Then the multimeter client containers should use VXLAN ID 42

  Scenario: VXLAN ID change propagates to client containers
    When the gluetun config "vxlan-id" is set to "100"
    Then the multimeter client containers should use VXLAN ID 100

  Scenario: Cluster CIDRs change propagates to client containers
    When the gluetun config "cluster-cidrs" is updated
    Then the multimeter client containers should use the new cluster CIDRs
