# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

Feature: Seerr charm deployment
  As a Juju operator
  I want to deploy the seerr charm
  So that I can manage media requests

  Scenario: Seerr deploys and awaits setup
    Given seerr is deployed
    Then seerr should be waiting for setup

  Scenario: API key secret is created
    Given seerr is deployed
    Then an api-key secret should exist for seerr

  Scenario: Status API is accessible
    Given seerr is deployed
    Then seerr status API should be accessible
