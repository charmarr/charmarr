# Backup

<span style="color: #FF6D00">:material-hammer-wrench: **Work in Progress**</span> — Track 1 does not include an integrated backup solution. Bring your own backup until Charmarr provides one.

## Smaller Blast Radius

Charmarr automatically configures apps through Juju relations, reducing what's lost if a config PVC is wiped:

| Restored automatically | Lost without backup |
|------------------------|---------------------|
| App connections (relations) | Library metadata (rescan to rebuild) |
| API keys (Juju secrets) | Watch history |
| Quality profiles (Recyclarr) | User accounts & preferences |
| Download client configs | Manual setting tweaks |
| Indexer configs | |

## Bring Your Own Backup

Options for backing up config PVCs:

- **CSI volume snapshots** — If your storage class supports it
- **kubectl cp** — Copy files from running pods
- **Restic / Kopia** — Direct backup to S3 or local storage
- **Velero** — `velero-backup-config` relation provided on all charms
