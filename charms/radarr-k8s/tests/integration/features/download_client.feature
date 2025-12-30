Feature: Radarr download client integration
  As a Juju operator
  I want to relate radarr to a download client via service mesh
  So that radarr can send movies to download

  Scenario: SABnzbd is registered as download client
    Given istio-k8s is deployed
    And istio-beacon is deployed
    And radarr is deployed
    And radarr is related to istio-beacon via service-mesh
    And sabnzbd is deployed
    And sabnzbd is related to istio-beacon via service-mesh
    And radarr is related to sabnzbd via download-client
    Then radarr should have sabnzbd registered as download client
