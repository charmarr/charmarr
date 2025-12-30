Feature: Radarr charm deployment
  As a Juju operator
  I want to deploy the radarr charm
  So that I can manage movie downloads

  Scenario: Radarr API is accessible
    Given radarr is deployed
    Then radarr API should return system status

  Scenario: API key secret is created
    Given radarr is deployed
    Then an api-key secret should exist for radarr
