Feature: Storage charm with native-nfs backend

  Background:
    Given the charmarr-multimeter charm is deployed
    And the charmarr-storage charm is deployed with native-nfs backend

  Scenario: Storage charm creates PV with NFS configuration
    Then a PV named "charmarr-shared-media-pv" should exist
    And the PV should have NFS server from config
    And the PV should have NFS path "/"
    And the PV should have reclaim policy "Retain"

  Scenario: Storage charm creates PVC bound to PV
    Then a PVC named "charmarr-shared-media" should exist in the model namespace
    And the PVC should be bound to PV "charmarr-shared-media-pv"
    And the PVC should have access mode "ReadWriteMany"

  Scenario: PVC becomes bound and charm is active
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

  Scenario: PV and PVC persist when charm is removed with cleanup-on-remove false
    Given cleanup-on-remove config is "false"
    When the storage charm is removed
    Then the PV "charmarr-shared-media-pv" should still exist
    And the PVC "charmarr-shared-media" should still exist

  Scenario: PV and PVC are deleted when charm is removed with cleanup-on-remove true
    Given cleanup-on-remove config is "true"
    When the storage charm is removed
    Then no PV named "charmarr-shared-media-pv" should exist
    And no PVC named "charmarr-shared-media" should exist

  Scenario: Non-leader unit shows standby status
    When the storage charm is scaled to 2 units
    Then the leader unit should be active
    And non-leader units should show "Standby" in status
