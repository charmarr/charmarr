# Pebble with LinuxServer.io Images

## Context and Problem Statement

Charmarr charms use LinuxServer.io container images (qBittorrent, SABnzbd, Radarr, Sonarr, Plex, etc.). These images use s6-overlay as their init system to handle:
- User/group creation from PUID/PGID environment variables
- Process supervision
- Graceful shutdown

However, Juju's Pebble also runs as PID 1 for process management. s6-overlay requires PID 1 to function, creating a conflict.

## Decision Drivers

- Pebble is the standard way to manage workloads in Juju K8s charms
- LinuxServer.io images are the de facto standard for media automation containers
- Need consistent file ownership across all apps sharing storage
- Must work with Kubernetes SecurityContext for volume permissions

## Considered Options

1. **Use Hotio images** - Alternative images that run binaries directly without init system
2. **Bypass s6-overlay** - Keep LinuxServer.io images but run application binaries directly, use Pebble for process management
3. **Custom images** - Build our own images without s6-overlay

## Decision Outcome

**Option 2: Bypass s6-overlay** - Keep LinuxServer.io images but run application binaries directly.

Pebble replaces s6-overlay's responsibilities:
- **Process user/group**: Pebble's `user-id`/`group-id` service options
- **Process supervision**: Pebble's service management
- **Volume permissions**: Kubernetes `fsGroup` in SecurityContext

## Implementation

### Two-Layer Permission Model

| Layer | Mechanism | Source | Purpose |
|-------|-----------|--------|---------|
| Process ownership | Pebble `user-id`/`group-id` | Storage relation PUID/PGID | Process runs as specific user |
| Volume permissions | K8s `fsGroup` | Storage relation PGID | Files on shared PVC accessible |

### PUID/PGID Source

| App Type | Source | Example Apps |
|----------|--------|--------------|
| Apps with storage relation | Storage charm's PUID/PGID | qBittorrent, SABnzbd, Radarr, Sonarr, Plex |
| Apps without storage relation | Hardcoded 1000:1000 | Overseerr, Prowlarr |

Apps without storage relations don't share files with other apps, so consistent ownership isn't required. The default 1000:1000 matches standard Linux first-user conventions.

### Pebble Layer Example

```python
def _build_pebble_layer(self) -> ops.pebble.LayerDict:
    """Build Pebble layer - bypasses s6, runs binary directly."""
    storage = self.media_storage.get_provider()

    return {
        "services": {
            "workload": {
                "override": "replace",
                "command": "/usr/bin/qbittorrent-nox --profile=/config",
                "startup": "enabled",
                "user-id": storage.puid,
                "group-id": storage.pgid,
                "environment": {
                    "HOME": "/config",
                    "TZ": "Etc/UTC",
                },
            }
        },
        "checks": {
            "workload-ready": {
                "override": "replace",
                "level": "ready",
                "http": {"url": "http://localhost:8080/api/v2/app/version"},
            }
        },
    }
```

### SecurityContext for Volume Permissions

```python
reconcile_storage_volume(
    manager=self.k8s,
    statefulset_name=self.app.name,
    namespace=self.model.name,
    container_name=CONTAINER_NAME,
    pvc_name=storage.pvc_name,
    mount_path=storage.mount_path,
    pgid=storage.pgid,  # Sets fsGroup in pod SecurityContext
)
```

### Finding Application Binaries

LinuxServer.io images install applications in standard locations:

| App | Binary Path |
|-----|-------------|
| qBittorrent | `/usr/bin/qbittorrent-nox` |
| SABnzbd | `/usr/bin/sabnzbdplus` (or check with `which sabnzbdplus`) |
| Radarr | `/app/radarr/bin/Radarr` |
| Sonarr | `/app/sonarr/bin/Sonarr` |
| Plex | `/usr/lib/plexmediaserver/Plex Media Server` |

To find the binary in a running container:
```bash
kubectl exec -n <namespace> <pod> -c <container> -- which <app-name>
# or
kubectl exec -n <namespace> <pod> -c <container> -- find /usr /app -name "<app-name>*" -type f
```

## Consequences

### Good

- Keep using well-maintained LinuxServer.io images
- Pebble provides consistent process management across all charms
- Clear separation: Pebble for process, fsGroup for volumes
- No custom image maintenance burden

### Bad

- Must discover binary paths for each application
- Lose s6-overlay's init scripts (may need to handle some setup in charm)
- HOME environment variable must be set explicitly

### Neutral

- Apps without storage relation use hardcoded 1000:1000 (acceptable since they don't share storage)

## Related ADRs

- [interfaces/adr-005-media-storage](../interfaces/adr-005-media-storage.md) - PUID/PGID in storage relation
- [storage/adr-003-pvc-patching](../storage/adr-003-pvc-patching-in-arr-charms.md) - SecurityContext patching
- [apps/adr-007-qbit-sabnzbd](adr-007-qbit-sabnzbd.md) - Download client implementation
- [apps/adr-004-radarr-sonarr](adr-004-radarr-sonarr.md) - Media manager implementation
