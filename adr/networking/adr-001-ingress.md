# Ingress Networking Architecture for Charmarr Stack

**Status:** Accepted

## Context and Problem Statement

Charmarr is a new media streaming infrastructure management system loosely based on the legacy psygoat-servarr Docker Compose stack from 2 years ago. The challenge is to design an ingress networking architecture that provides secure access to media services (Radarr, Sonarr, Prowlarr, Overseerr, Plex/Jellyfin, and download clients) with differentiated access control for different user groups, remote access via Tailscale, integration with Canonical's Charmed Istio service mesh, and full automation through Terraform without manual configuration steps.

## Considered Options

* **Option 1: Single Istio Ingress Gateway with Tailscale Operator** - Use Charmed Istio's Kubernetes Gateway API-based ingress as the edge for all services, with the Tailscale operator exposing only the Istio ingress gateway to the tailnet. Services remain behind Istio, accessible only through the single Tailscale-exposed gateway.

* **Option 2: Direct Tailscale Service Exposure** - Use the Tailscale operator to expose each individual Charmarr service directly to the tailnet without an intermediate ingress layer. Each service would get its own Tailscale proxy device.

* **Option 3: Multiple Ingress Gateways with Selective Exposure** - Deploy separate Istio ingress gateways for different service groups with distinct security and access requirements, allowing selective exposure through Tailscale with differentiated access control policies per gateway.

* **Option 4: NodePort or LoadBalancer Services** - Use basic Kubernetes NodePort or LoadBalancer services without Istio, exposing services via local IPs and then routing through Tailscale.

## Decision Outcome

Chosen option: "Option 3: Multiple Ingress Gateways with Selective Exposure", because it provides granular security boundaries, enables differentiated access control for different user groups, and maintains flexibility while leveraging charms and Terraform to minimize operational complexity.

### Architecture Details

Three separate Istio ingress gateways deployed as istio-ingress-k8s charm instances serve distinct security domains. The arr-gateway fronts content management services (Radarr, Sonarr, Prowlarr, Overseerr) with permissive Tailscale ACLs for family access. The media-gateway serves streaming services (Plex/Jellyfin) with moderate ACL restrictions. The admin-gateway provides access to download clients (qBittorrent, SABnzbd) with highly restrictive ACLs for administrators only or remains LAN-only.

Each gateway is a separate Kubernetes Service (type LoadBalancer) with its own local IP address. Kubernetes Gateway API HTTPRoute resources attach services to the appropriate gateway based on security classification. All charmed arr services (Radarr, Sonarr, Prowlarr, Overseerr, qBittorrent, SABnzbd) and media streaming services (Plex/Jellyfin) communicate within the Istio service mesh via mTLS, while the Tailscale operator itself remains outside the mesh and is deployed via Terraform's Helm provider rather than being charmed.

A custom tailscale-connector workload-less charm automates Tailscale exposure and operates outside the service mesh. The Istio ingress charm provides a gateway-metadata relation containing gateway name, namespace, and service name. When related to the tailscale-connector, the connector checks Tailscale operator readiness and annotates the ingress gateway's LoadBalancer Service with Tailscale exposure annotations. The connector manages multiple gateways simultaneously and removes annotations when relations are broken. Access control is implemented via Tailscale ACL policies using device tags (tag:family, tag:viewer, tag:admin) assigned to user devices.

Terraform deploys the Tailscale operator via Helm provider with OAuth credentials from secure secrets management, deploys all charms via Juju provider, and establishes relations between gateways and the tailscale-connector charm for fully automated provisioning without manual steps.

### Consequences

* Good, because separate gateways create clear security boundaries allowing family access to content management while restricting admin tools to administrators via Tailscale ACL policies with device tags.

* Good, because the tailscale-connector charm fully automates Tailscale exposure through Juju relations, eliminating manual annotation and configuration steps.

* Good, because Istio mesh provides mTLS between services with observability that integrates with Canonical's Observability Stack, and each gateway can be independently monitored.

* Good, because charm abstraction makes deploying three gateways simple (three charm instances in Terraform) and supports future expansion with additional gateways without refactoring.

* Good, because Tailscale provides zero-trust network access without exposing services to public internet while supporting differentiated access policies per gateway.

* Good, because architecture is fully declarative through Terraform enabling consistent automated deployments without manual intervention.

* Bad, because managing Tailscale ACL policies adds configuration surface to maintain, document, and audit as users and devices change.

* Bad, because troubleshooting network issues requires determining which gateway path traffic should take across multiple layers (gateway, Tailscale proxy, routing, ACL policy).

* Bad, because three gateways consume more cluster resources (CPU, memory, LoadBalancer IPs) than a single gateway, though this enables independent scaling and optimization per gateway.

* Bad, because custom domains with Tailscale require separate DNS and TLS certificate management as Tailscale's native HTTPS only works with ts.net domains.
