# Charmarr Storage Architecture

This directory contains the architectural decision records (ADRs) for Charmarr's storage design, covering shared media volumes, configuration persistence, and backup strategies.

## Architecture Overview

Charmarr's storage layer provides:
- **Shared Media Storage**: Single PVC mounted by all media applications for hardlink support
- **Config Storage**: Separate per-charm storage for databases and configuration
- **Trash Guides Compliance**: Directory structure follows media automation best practices
- **Backup Strategy**: Automated configuration backup with restore procedures

## ADRs

### Shared Media Storage
- **[ADR-001: Shared PVC Architecture](adr-001-shared-pvc-architecture.md)** - Single shared PVC for all media apps to enable hardlinks
- **[ADR-002: Charmarr Storage Charm](adr-002-charmarr-storage-charm.md)** - Charm that manages and provides the shared PVC
- **[ADR-003: PVC Patching in Arr Charms](adr-003-pvc-patching-in-arr-charms.md)** - How consumer charms mount the shared PVC

### Configuration Storage
- **[ADR-004: Config Storage](adr-004-config-storage.md)** - Separate storage for charm configuration and databases
- **[ADR-005: Config Backup](adr-005-config-backup.md)** - Automated backup and restore procedures

## Storage Architecture

### Shared Media Layout
```
/data (shared PVC mounted by all charms)
├── torrents/
│   ├── movies/
│   ├── tv/
│   └── music/
├── usenet/
│   ├── incomplete/
│   └── complete/
│       ├── movies/
│       ├── tv/
│       └── music/
└── media/
    ├── movies/
    ├── tv/
    └── music/
```

### Access Modes
- **ReadWriteMany (RWX)**: For NFS-backed storage, allows pods on any node
- **ReadWriteOnce (RWO)**: For local storage, all pods must run on same node

## Key Design Principles

1. **Hardlink Support**: All media apps share same filesystem to enable hardlinks (Trash Guides requirement)
2. **Separation of Concerns**: Media storage (shared) vs config storage (per-charm)
3. **Declarative Patching**: Consumer charms patch their own Kubernetes resources to mount shared PVC
4. **Storage Agnostic**: Works with NFS, TopoLVM, local-path, or any Kubernetes storage provider
5. **Infrastructure Redundancy**: Data protection implemented at filesystem layer (ZFS, RAID), not Kubernetes

## Multi-Node Considerations

For **multi-node clusters**, use NFS (RWX) to allow pods across nodes. With local storage (RWO), all media app pods must run on the same node, defeating multi-node distribution.
