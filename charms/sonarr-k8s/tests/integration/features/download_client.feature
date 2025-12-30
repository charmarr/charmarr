Feature: Sonarr download client integration
  As a Juju operator
  I want to relate sonarr to a download client via service mesh
  So that sonarr can send TV series to download

  Scenario: SABnzbd is registered as download client
    Given istio-k8s is deployed
    And istio-beacon is deployed
    And sonarr is deployed
    And sonarr is related to istio-beacon via service-mesh
    And sabnzbd is deployed
    And sabnzbd is related to istio-beacon via service-mesh
    And sonarr is related to sabnzbd via download-client
    Then sonarr should have sabnzbd registered as download client
