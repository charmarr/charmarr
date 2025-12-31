# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

Feature: Overseerr charm deployment
  As a Juju operator
  I want to deploy the overseerr charm
  So that I can manage media requests

  Scenario: Overseerr deploys and awaits setup
    Given overseerr is deployed
    Then overseerr should be waiting for setup

  Scenario: API key secret is created
    Given overseerr is deployed
    Then an api-key secret should exist for overseerr

  Scenario: Status API is accessible
    Given overseerr is deployed
    Then overseerr status API should be accessible
