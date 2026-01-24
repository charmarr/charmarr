Feature: Charmarr Stack Deployment
  Test the charmarr terraform module deploys a functional media stack.

  Scenario: Baseline deployment
    Given the charmarr module is deployed
    Then all apps except plex and overseerr should be active
    And plex and overseerr should be waiting

  Scenario: Deployment with VPN
    Given the charmarr module is deployed with VPN
    Then all apps except plex and overseerr should be active
    And plex and overseerr should be waiting

  Scenario: Deployment with VPN and Istio
    Given the charmarr module is deployed with VPN and Istio
    Then all apps except plex and overseerr should be active
    And plex and overseerr should be waiting
