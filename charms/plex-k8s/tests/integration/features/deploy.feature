Feature: Plex charm deployment
  As a Juju operator
  I want to deploy the plex charm
  So that I can stream media to devices

  Scenario: Plex identity endpoint is accessible
    Given plex is deployed
    Then plex identity endpoint should respond

  Scenario: Plex shows unclaimed status when not claimed
    Given plex is deployed
    Then plex should show unclaimed status
