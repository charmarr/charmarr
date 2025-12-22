Feature: Storage charm with storage-class backend

  Background:
    Given the charmarr-storage charm is deployed with storage-class backend
    And the charmarr-multimeter charm is deployed

  Scenario: Storage charm creates PVC in Kubernetes
    Then a PVC named "charmarr-shared-media" should exist in the model namespace
    And the PVC should use the configured storage class
    And the PVC should have the configured access mode
    And the PVC should have the configured size

  Scenario: PVC becomes bound and charm is active
    When charmarr-multimeter is related to charmarr-storage via media-storage
    Then the PVC "charmarr-shared-media" should be in "Bound" phase
    And the storage charm should be active

  Scenario: Storage charm publishes relation data when related
    When charmarr-multimeter is related to charmarr-storage via media-storage
    Then the storage charm should be active
    And the multimeter charm should be active

  Scenario: Relation data contains correct storage information
    Given charmarr-multimeter is related to charmarr-storage via media-storage
    Then the media-storage relation should contain pvc_name "charmarr-shared-media"
    And the media-storage relation should contain mount_path "/data"
    And the media-storage relation should contain puid 1000
    And the media-storage relation should contain pgid 1000

  Scenario: Storage volume is mounted in related application
    Given charmarr-multimeter is related to charmarr-storage via media-storage
    Then the multimeter pod should have "/data" mounted

  Scenario: Storage volume is unmounted when relation is removed
    Given charmarr-multimeter is related to charmarr-storage via media-storage
    When the media-storage relation is removed
    Then the multimeter pod should not have "/data" mounted
    And the storage charm should be active

  Scenario: Resize failure is handled gracefully
    Given charmarr-multimeter is related to charmarr-storage via media-storage
    When the storage charm config "size" is set to "200Gi" expecting blocked
    Then the storage charm should be blocked with message containing "resize"

  Scenario: Resize error clears when config matches PVC
    Given the storage charm is blocked due to resize failure
    When the storage charm config "size" is set to the current PVC size
    Then the storage charm should be active

  Scenario: PVC persists when charm is removed with cleanup-on-remove false
    Given cleanup-on-remove config is "false"
    When the storage charm is removed
    Then the PVC "charmarr-shared-media" should still exist

  Scenario: PVC is deleted when charm is removed with cleanup-on-remove true
    Given cleanup-on-remove config is "true"
    When the storage charm is removed
    Then no PVC named "charmarr-shared-media" should exist

  Scenario: Non-leader unit shows standby status
    When the storage charm is scaled to 2 units
    Then the leader unit should be active
    And non-leader units should show "Standby" in status
