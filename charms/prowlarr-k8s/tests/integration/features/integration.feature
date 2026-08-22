Feature: Prowlarr Media Indexer Integration
  Test that prowlarr-k8s provides indexers to media managers.

  Background:
    Given charmarr-storage is deployed
    And prowlarr is deployed
    And radarr is deployed with storage
    And radarr is related to prowlarr via media-indexer

  Scenario: Prowlarr has Radarr registered as application
    Then prowlarr should have radarr registered as an application
