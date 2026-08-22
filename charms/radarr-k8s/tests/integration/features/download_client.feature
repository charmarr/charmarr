Feature: Radarr download client integration
  As a Juju operator
  I want to relate radarr to a download client
  So that radarr can send movies to download

  Scenario: SABnzbd is registered as download client
    Given radarr is deployed
    And sabnzbd is deployed
    And radarr is related to sabnzbd via download-client
    Then radarr should have sabnzbd registered as download client
