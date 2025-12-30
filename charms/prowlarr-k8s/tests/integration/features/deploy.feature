Feature: Prowlarr Deployment
  Test that prowlarr-k8s deploys correctly.

  Background:
    Given prowlarr is deployed

  Scenario: Charm becomes active
    Then the prowlarr charm should be active

  Scenario: API key secret is created
    Then an api-key secret should exist for prowlarr
