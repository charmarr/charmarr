Feature: SABnzbd Deployment
  Test that sabnzbd-k8s deploys correctly and provides download-client interface.

  Background:
    Given charmarr-storage is deployed
    And sabnzbd is deployed with storage relation

  Scenario: Charm becomes active with storage
    Then the sabnzbd charm should be active

  Scenario: API accessible with key
    Given the charmarr-multimeter charm is deployed
    When the API key is retrieved from the sabnzbd secret
    Then the sabnzbd API should respond successfully

  Scenario: Download-client provider data is published
    Given the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to sabnzbd via download-client
    Then the download-client relation should contain api_url
    And the download-client relation should contain api_key_secret_id
    And the download-client relation should contain client type "sabnzbd"
