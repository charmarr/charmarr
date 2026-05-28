# Charmarr Library Architecture

This directory contains the architectural decision records (ADRs) for shared code libraries used across Charmarr charms.

## Architecture Overview

Charmarr's library layer provides:
- **Shared Arr Infrastructure**: Common API clients, reconcilers, and config builders for arr applications
- **VPN Integration Library**: Reusable VPN gateway integration for download clients
- **Interface Implementations**: Concrete relation interface classes and data models
- **Code Reuse**: Eliminates duplication across similar charms (Radarr/Sonarr/Lidarr share ~95% code)

## ADRs

### Core Libraries
- **[ADR-001: Shared Arr Code](adr-001-shared-arr-code.md)** - API clients, reconcilers, and config builders for arr applications (Radarr, Sonarr, Prowlarr)
- **[ADR-002: VPN K8s Library](adr-002-vpn-k8s-lib.md)** - VPN gateway integration library with pod-gateway VXLAN patching
- **[ADR-003: Reconciliation Philosophy](adr-003-reconciliation-philosophy.md)** - When to use aggressive vs respectful vs self-healing reconciliation patterns

## Library Structure

### charmarr-lib
```
charmarr-lib/
├── interfaces/
│   ├── media_indexer.py        # MediaIndexer interface + data models
│   ├── download_client.py      # DownloadClient interface + MEDIA_TYPE_DOWNLOAD_PATHS
│   ├── media_manager.py        # MediaManager interface
│   ├── media_storage.py        # MediaStorage interface
│   └── vpn_gateway.py          # VPNGateway interface
├── arr/
│   ├── base_client.py          # BaseArrApiClient (HTTP mechanics)
│   ├── api_client.py           # ArrApiClient (Radarr/Sonarr/Lidarr v3 API)
│   ├── prowlarr_client.py      # ProwlarrApiClient (Prowlarr v1 API)
│   ├── reconcilers.py          # Declarative reconciliation functions
│   └── config_builders.py      # Relation data → API payload transformation
└── reconciler.py               # observe_events utilities
```

### vpn-k8s-lib
Provides interface classes, data models, and Kubernetes resource patching helpers for both VPN gateway providers and consumers.

## Key Design Principles

1. **Inheritance for API Clients**: `BaseArrApiClient` handles HTTP, subclasses add app-specific endpoints
2. **Aggressive Declarative Reconciliation**: Relations are single source of truth, all other config is removed
3. **Stateless Operations**: Reconcilers are idempotent and safe to call repeatedly
4. **Separation of Concerns**: API clients, reconcilers, and config builders are separate modules
5. **Reusability**: Libraries work beyond Charmarr ecosystem, usable by any Juju charm

## Shared Constants

- **MEDIA_TYPE_DOWNLOAD_PATHS**: Maps media managers to download folder names (radarr → movies, sonarr → tv)
- **MEDIA_MANAGER_IMPLEMENTATIONS**: Maps media managers to Prowlarr application implementation details
