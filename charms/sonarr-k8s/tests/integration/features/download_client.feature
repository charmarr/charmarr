Feature: Sonarr download client integration
  As a Juju operator
  I want to relate sonarr to a download client
  So that sonarr can send TV series to download

  Scenario: SABnzbd is registered as download client
    Given sonarr is deployed
    And sabnzbd is deployed
    And sonarr is related to sabnzbd via download-client
    Then sonarr should have sabnzbd registered as download client
