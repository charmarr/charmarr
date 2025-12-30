Feature: Prowlarr Media Indexer Integration
  Test that prowlarr-k8s provides indexers to media managers via service mesh.

  Background:
    Given istio-k8s is deployed
    And istio-beacon is deployed
    And charmarr-storage is deployed
    And prowlarr is deployed
    And prowlarr is related to istio-beacon via service-mesh
    And radarr is deployed with storage
    And radarr is related to istio-beacon via service-mesh
    And radarr is related to prowlarr via media-indexer

  Scenario: Prowlarr has Radarr registered as application
    Then prowlarr should have radarr registered as an application
