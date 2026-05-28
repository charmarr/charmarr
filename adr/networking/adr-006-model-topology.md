# Multi-Model Deployment Topology

**Status:** Accepted

## Context and Problem Statement

Charmarr consists of content management services (arr stack, media servers) and download clients with VPN requirements. These have different security profiles, update cadences, and operational concerns. How should we organize these services across Juju models to balance separation of concerns with operational simplicity?

Related: See [ADR-001: Ingress Architecture](adr-001-ingress.md) for ingress gateway placement.

## Considered Options

* **Single model (charmarr)** - All services in one Juju model/namespace
* **Multi-model (charmarr-core + charmarr-downloads)** - Split by functional domain
* **Per-service models** - Each service (Radarr, Sonarr, etc.) in its own model
* **Per-security-domain models** - Models based on security requirements (public, internal, admin)

## Decision Outcome

Chosen option: **"Multi-model (charmarr-core + charmarr-downloads)"**, because it provides clear separation between stable content management services and VPN-dependent download infrastructure, isolates VPN complexity, allows independent scaling and upgrades, while keeping related services together for observability and relation management.

### Consequences

* Good, because VPN complexity isolated in charmarr-downloads model
* Good, because download clients can be upgraded/scaled independently of core stack
* Good, because namespace-level security policies can differ (NetworkPolicy, mesh enrollment)
* Good, because clearer operational boundaries (core vs downloads responsibilities)
* Good, because download clients still in mesh, communicate securely with core services
* Good, because ingress gateways (from ADR-001) remain in charmarr-core with their consumers
* Bad, because requires cross-model relations (Juju offers/consumes)
* Bad, because two namespaces to monitor instead of one
* Bad, because user must manage mesh enrollment correctly for both namespaces

**Model 1: charmarr-core**
* Services: Radarr, Sonarr, Lidarr, Prowlarr, Overseerr, Plex/Jellyfin
* Services: arr-gateway, media-gateway, admin-gateway (from ADR-001)
* Namespace: Enrolled in Istio Ambient mesh
* Purpose: Stable content management and serving stack

**Model 2: charmarr-downloads**
* Services: qBittorrent, SABnzbd, vpnarr
* Namespace (download clients): Enrolled in Istio Ambient mesh
* Namespace (vpnarr): NOT enrolled in mesh (separate namespace)
* Purpose: VPN-dependent download infrastructure

**Cross-model relations:**
```bash
# In charmarr-core
juju offer radarr:download-client

# In charmarr-downloads
juju consume charmarr-core.radarr
juju relate qbittorrent radarr
```

**Rejected alternatives:**
* Single model: VPN complexity bleeds into core stack, harder to reason about, single namespace means single mesh enrollment decision
* Per-service models: Too granular, excessive cross-model relations, operational overhead, loses observability benefits of colocated services
* Per-security-domain: Doesn't align with functional boundaries, download clients need to communicate with core services frequently (creates cross-cutting concerns)

**Operational clarity:**
* Core stack stable → Infrequent updates
* Download clients + VPN → More frequent tuning (providers, configs)
* Clear blast radius if VPN changes break something
* Independent backup/restore strategies if needed
