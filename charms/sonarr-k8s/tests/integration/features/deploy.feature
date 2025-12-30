Feature: Sonarr charm deployment
  As a Juju operator
  I want to deploy the sonarr charm
  So that I can manage TV series downloads

  Scenario: Sonarr API is accessible
    Given sonarr is deployed
    Then sonarr API should return system status

  Scenario: API key secret is created
    Given sonarr is deployed
    Then an api-key secret should exist for sonarr
