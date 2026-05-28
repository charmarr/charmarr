# Charmarr Applications Architecture

This directory contains the architectural decision records (ADRs) for Charmarr's application implementations, covering media managers, download clients, media servers, and supporting infrastructure.

## Architecture Overview

Charmarr's application layer provides:
- **Media Managers**: Radarr (movies), Sonarr (TV), with future support for Lidarr and others
- **Download Clients**: qBittorrent (torrents) and SABnzbd (usenet) with VPN routing
- **Media Servers**: Plex for streaming, with Jellyfin support planned
- **Request Management**: Overseerr for user-facing content requests
- **Supporting Infrastructure**: Prowlarr for indexer management, charmarr-storage for shared media access, Tailscale for remote connectivity

## ADRs

### Project Scope
- **[ADR-001: V1 Application Scope](adr-001-v1-apps.md)** - Defines which applications are included in v1 release and future roadmap

### Core Infrastructure
- **[ADR-002: Cross-App Authentication](adr-002-cross-app-auth.md)** - API key management and secure secret sharing between charms
- **[ADR-003: Recyclarr Integration](adr-003-recyclarr-integration.md)** - Automated quality profile and custom format synchronization
- **[ADR-005: Charmarr Storage](adr-005-charmarr-storage.md)** - Shared media storage charm implementation
- **[ADR-006: Gluetun K8s](adr-006-gluetun-k8s.md)** - VPN gateway charm using gluetun and pod-gateway

### Media Managers
- **[ADR-004: Radarr/Sonarr](adr-004-radarr-sonarr.md)** - Media manager charm implementation with reconciler pattern

### Download Clients
- **[ADR-007: qBittorrent/SABnzbd](adr-007-qbit-sabnzbd.md)** - Download client implementation with VPN integration

### Indexers
- **[ADR-008: Prowlarr](adr-008-prowlarr.md)** - Central indexer manager charm

### Media Servers
- **[ADR-009: Plex](adr-009-plex.md)** - Plex media server charm implementation

### Request Management
- **[ADR-010: Overseerr](adr-010-overseer.md)** - Content request interface charm

### Networking
- **[ADR-011: Tailscale Connector](adr-011-tailscale-connector.md)** - Tailscale mesh integration for remote access

### Scaling
- **[ADR-012: App Scaling V1](adr-012-app-scaling-v1.md)** - Initial scaling approach
- **[ADR-013: App Scaling V2](adr-013-app-scaling-v2.md)** - Advanced scaling patterns for multiple instances

## Key Design Principles

1. **Reconciler Pattern**: All charms use a unified reconciler approach with declarative configuration
2. **Interface-Based Integration**: Charms communicate via well-defined Juju relations (media-indexer, download-client, etc.)
3. **Shared Infrastructure**: Common code in charmarr-lib eliminates duplication across similar applications
4. **VPN-First Downloads**: All download clients route through VPN gateway with kill-switch protection
5. **Automated Configuration**: Recyclarr integration ensures quality profiles and formats stay current
6. **Secrets Management**: API keys and credentials managed via Juju secrets, shared securely between charms
