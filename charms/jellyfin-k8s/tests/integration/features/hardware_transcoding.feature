Feature: Jellyfin hardware transcoding configuration
  As a Juju operator
  I want to enable hardware transcoding
  So that Jellyfin can use Intel QuickSync for efficient video encoding

  Scenario: Enabling hardware transcoding adds dev-dri volume
    Given jellyfin is deployed
    When hardware-transcoding is enabled
    Then the jellyfin StatefulSet should have dev-dri volume mount

  Scenario: Disabling hardware transcoding removes dev-dri volume
    Given jellyfin is deployed
    When hardware-transcoding is disabled
    Then the jellyfin StatefulSet should not have dev-dri volume mount
