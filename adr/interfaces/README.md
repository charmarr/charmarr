# Charmarr Interface Architecture

This directory contains the architectural decision records (ADRs) for Charmarr's Juju relation interface definitions, enabling capability-based integration between charms.

## Architecture Overview

Charmarr's interface layer provides:
- **Capability-Based Design**: Interfaces represent capabilities (media-indexer, download-client) rather than specific applications
- **Workload-Agnostic**: Interface contracts allow drop-in replacements without charm changes
- **Secure Data Exchange**: Secret management built into relation data models
- **Multiple Implementations**: Same interface supports different providers (qBittorrent, SABnzbd both provide download-client)

## ADRs

### Core Framework
- **[ADR-001: Charmarr Interfaces](adr-001-charmarr-interfaces.md)** - Capability-based interface taxonomy and design principles
- **[ADR-002: Secret Management](adr-002-secret-management.md)** - Secure credential sharing between charms via Juju secrets

### Interface Definitions
- **[ADR-003: Media Indexer](adr-003-media-indexer.md)** - Indexer configuration synchronization (Prowlarr ↔ arr apps)
- **[ADR-004: Download Client](adr-004-download-client.md)** - Download job submission and monitoring
- **[ADR-005: Media Storage](adr-005-media-storage.md)** - Shared filesystem access for hardlinks
- **[ADR-006: Media Manager](adr-006-media-manager.md)** - Content request submission (Overseerr → Radarr/Sonarr)
- **[ADR-007: VPN Gateway](adr-007-vpn-gateway.md)** - VPN-routed network traffic for download clients

## Interface Map

| Interface | Purpose | Providers | Requirers |
|-----------|---------|-----------|-----------|
| **media-indexer** | Share indexer definitions and enable sync | Prowlarr | Radarr, Sonarr, Lidarr |
| **download-client** | Submit download jobs | qBittorrent, SABnzbd | All media managers |
| **media-storage** | Mount shared media filesystem | charmarr-storage | All media apps |
| **vpn-gateway** | Route traffic through VPN | gluetun-k8s | Download clients |
| **media-manager** | Submit user content requests | Radarr, Sonarr, Lidarr | Overseerr, Jellyseerr |

## Key Design Principles

1. **Capability Over Identity**: Interface names describe what they do (media-indexer), not which app provides them (prowlarr-indexer)
2. **Strict Scope Discipline**: Each interface has exactly one well-defined purpose
3. **Bidirectional Within Scope**: Both sides can publish data, but only relevant to that interface's purpose
4. **Multiple Instance Support**: Interfaces handle multiple instances of the same app type via instance naming
5. **Extensibility**: Alternative implementations can satisfy the same interface without changes
