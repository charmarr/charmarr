# Charmarr Networking Architecture

This directory contains the architectural decision records (ADRs) for Charmarr's networking design, covering ingress, egress, service mesh integration, and deployment topology.

## Architecture Overview

Charmarr's networking architecture provides:
- **Ingress**: Three-gateway design with Tailscale for remote access, segmented by security domain
- **Egress**: VPN routing for download clients via VXLAN overlay using gluetun + pod-gateway
- **Service Mesh**: Istio Ambient for mTLS and observability, coexisting with VPN routing
- **Topology**: Multi-model separation (core + downloads) for operational clarity

## ADRs

### Ingress
- **[ADR-001: Ingress Architecture](adr-001-ingress.md)** - Three Istio gateways (arr/media/admin) with Tailscale integration

### VPN Egress
- **[ADR-002: VPN Gateway Solution](adr-002-vpn-gateway.md)** - gluetun as centralized gateway with VXLAN overlay via pod-gateway
- **[ADR-003: Download Client Integration](adr-003-download-client-egress.md)** - Consumer self-patching via vpn-k8s-lib + lightkube
- **[ADR-004: VPN Kill Switch](adr-004-vpn-kill-switch.md)** - Two-layer defense: consumer-owned NetworkPolicy + gluetun firewall

### Service Mesh
- **[ADR-005: Istio Mesh Integration](adr-005-istio-mesh-vpn-integration.md)** - Download clients IN mesh, gateway OUT; routing layer separation enables coexistence

### Topology
- **[ADR-006: Multi-Model Topology](adr-006-model-topology.md)** - charmarr-core + charmarr-downloads models with cross-model relations

### Interfaces
- **[ADR-007: VPN Gateway Interface](../interfaces/adr-007-vpn-gateway.md)** - vpn-k8s-lib providing interface classes, data models, and patching helpers for both provider and consumer

## Component Summary

| Component | Description |
|-----------|-------------|
| **gluetun-k8s** | Charm running gluetun container (VPN client). Gets patched by vpn-k8s-lib to add pod-gateway gateway containers. |
| **vpn-k8s-lib** | Python package with interface classes, data models, and patching logic for both gateway and client sides. |
| **Consumer charms** | Use VPNGatewayRequirer from vpn-k8s-lib to patch themselves with pod-gateway client containers + NetworkPolicy. |
| **pod-gateway** | Container image providing VXLAN overlay scripts for both gateway and client sides. |

## Key Design Principles

1. **Defense in Depth**: Multiple enforcement points (NetworkPolicy at consumer, firewall at gateway)
2. **Layer Separation**: Routing decisions (L3) before ztunnel interception (L4+), enabling VXLAN ↔ Istio coexistence
3. **Declarative Topology**: Juju relations make VPN routing visible via `juju status --relations`
4. **Resource Ownership**: Each charm patches its own Kubernetes resources (no cross-charm modification)
5. **Extensibility**: Routing method communicated via relation data, allowing future alternatives without charm changes

## Traffic Flow Summary

```
External traffic (qBittorrent → tracker):
  qBittorrent pod
    → routing table: default via vxlan0
    → VXLAN encapsulation (outer dst = gluetun pod IP)
    → gluetun pod receives, decapsulates
    → routes through tun0 (VPN tunnel)
    → exits via VPN provider

Internal traffic (qBittorrent → Radarr):
  qBittorrent pod
    → routing table: cluster CIDR via eth0
    → ztunnel intercepts (mesh enrolled)
    → mTLS to Radarr's ztunnel
    → Radarr pod receives

Kill switch (routing failure):
  qBittorrent pod
    → VXLAN route missing/broken
    → traffic tries default route (eth0 to internet)
    → NetworkPolicy blocks (dst not in cluster CIDR)
    → BLOCKED ✅

Kill switch (VPN disconnection):
  qBittorrent pod
    → VXLAN route works
    → traffic reaches gluetun pod
    → gluetun's tun0 is down
    → gluetun firewall blocks non-VPN egress
    → BLOCKED ✅
```

## Image Versions

| Image | Version | Purpose |
|-------|---------|---------|
| gluetun | `ghcr.io/qdm12/gluetun:latest` | VPN client (creates tun0) |
| pod-gateway | `ghcr.io/angelnu/pod-gateway:v1.13.0` | VXLAN overlay scripts |

## Reading Order

Suggested order for understanding the complete architecture:
1. ADR-001 (ingress foundation)
2. ADR-002 → ADR-003 → ADR-004 (VPN egress stack)
3. ADR-007 (interface and library structure)
4. ADR-005 (mesh integration)
5. ADR-006 (topology)
