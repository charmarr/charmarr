Feature: Radarr recyclarr integration
  As a Juju operator
  I want to configure radarr with recyclarr
  So that quality profiles are automatically managed

  Scenario: Recyclarr config is applied
    Given radarr is deployed
    And radarr is configured with trash-profiles "hd-bluray-web"
    When recyclarr config action is run on radarr
    Then radarr should have quality profiles configured
