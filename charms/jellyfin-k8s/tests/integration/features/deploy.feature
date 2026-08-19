Feature: Jellyfin charm deployment
  As a Juju operator
  I want to deploy the jellyfin charm
  So that I can stream media to devices

  Scenario: Jellyfin public info endpoint is accessible
    Given jellyfin is deployed
    Then jellyfin public info endpoint should respond

  Scenario: Jellyfin completes its own startup wizard
    Given jellyfin is deployed
    Then jellyfin should report the startup wizard as completed
    And an api-key secret should exist for jellyfin
