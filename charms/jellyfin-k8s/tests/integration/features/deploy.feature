Feature: Jellyfin charm deployment
  As a Juju operator
  I want to deploy the jellyfin charm
  So that I can stream media to devices

  Scenario: Jellyfin public info endpoint is accessible
    Given jellyfin is deployed
    Then jellyfin public info endpoint should respond

  Scenario: Jellyfin shows setup-incomplete status before the wizard is done
    Given jellyfin is deployed
    Then jellyfin should show setup-incomplete status
