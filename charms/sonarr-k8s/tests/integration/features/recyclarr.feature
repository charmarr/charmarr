Feature: Sonarr recyclarr integration
  As a Juju operator
  I want to configure sonarr with recyclarr
  So that quality profiles are automatically managed

  Scenario: Recyclarr config is applied
    Given sonarr is deployed
    And sonarr is configured with trash-profiles "web-1080p"
    When recyclarr config action is run on sonarr
    Then sonarr should have quality profiles configured
