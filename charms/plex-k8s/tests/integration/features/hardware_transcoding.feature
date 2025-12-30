Feature: Plex hardware transcoding configuration
  As a Juju operator
  I want to enable hardware transcoding
  So that Plex can use Intel QuickSync for efficient video encoding

  Scenario: Enabling hardware transcoding adds dev-dri volume
    Given plex is deployed
    When hardware-transcoding is enabled
    Then the plex StatefulSet should have dev-dri volume mount

  Scenario: Disabling hardware transcoding removes dev-dri volume
    Given plex is deployed
    When hardware-transcoding is disabled
    Then the plex StatefulSet should not have dev-dri volume mount
