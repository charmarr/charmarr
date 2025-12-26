Feature: qBittorrent Deployment
  Test that qbittorrent-k8s deploys correctly and provides download-client interface.

  Background:
    Given charmarr-storage is deployed
    And qbittorrent is deployed with storage relation

  Scenario: Charm becomes active with storage
    Then the qbittorrent charm should be active

  Scenario: WebUI accessible with credentials
    Given the charmarr-multimeter charm is deployed
    When credentials are retrieved from the qbittorrent secret
    Then the qbittorrent WebUI should authenticate successfully

  Scenario: Download-client provider data is published
    Given the charmarr-multimeter charm is deployed
    And charmarr-multimeter is related to qbittorrent via download-client
    Then the download-client relation should contain api_url
    And the download-client relation should contain credentials_secret_id
    And the download-client relation should contain client type "qbittorrent"
