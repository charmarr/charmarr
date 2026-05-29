# Charmarr Architecture Decision Records

This directory contains all architectural decision records (ADRs) for the Charmarr project, documenting key design choices, their context, alternatives considered, and consequences.

## What are ADRs?

Architecture Decision Records capture important architectural decisions made during the project's development. Each ADR documents:
- **Context**: The problem or situation requiring a decision
- **Considered Options**: Alternative approaches evaluated
- **Decision Outcome**: The chosen solution and rationale
- **Consequences**: Positive and negative implications of the decision

## Directory Structure

ADRs are organized by concern area:

| Directory | Focus Area | Key Decisions |
|-----------|------------|---------------|
| **[apps/](apps/)** | Application implementations | Media managers, download clients, media servers, request management |
| **[interfaces/](interfaces/)** | Juju relation contracts | Capability-based interface design, secret management |
| **[lib/](lib/)** | Shared code libraries | Arr infrastructure, VPN integration |
| **[networking/](networking/)** | Network architecture | Ingress, VPN egress, service mesh, topology |
| **[storage/](storage/)** | Storage design | Shared PVC, config storage, backup |
| **[ops/](ops/)** | CI/CD operations | CI auto-healing, developer automation |
| **[o11y/](o11y/)** | Observability | COS integration, per-app exporters, dashboards, alerts, SLI/SLO catalog |
| **[oauth/](oauth/)** | Authentication | OAuth integration (planned) |

Each subdirectory contains its own README with detailed architecture overview and ADR index.

## Reading Recommendations

**New to Charmarr?** Start with:
1. [apps/adr-001-v1-apps.md](apps/adr-001-v1-apps.md) - Project scope and application stack
2. [interfaces/adr-001-charmarr-interfaces.md](interfaces/adr-001-charmarr-interfaces.md) - Interface design philosophy
3. [networking/README.md](networking/README.md) - Networking architecture overview

**Understanding specific areas:**
- **Application integration**: [interfaces/](interfaces/) → [lib/](lib/) → [apps/](apps/)
- **Network traffic flow**: [networking/README.md](networking/README.md) for comprehensive guide
- **Storage architecture**: [storage/adr-001-shared-pvc-architecture.md](storage/adr-001-shared-pvc-architecture.md)

## ADR Naming Convention

ADRs follow the pattern: `adr-NNN-descriptive-name.md`
- Sequential numbering within each directory
- Descriptive kebab-case names
- Markdown format with consistent structure

## Cross-References

ADRs frequently reference related decisions. Look for:
- **Related ADRs** sections linking to dependencies
- **See also** references to complementary decisions
- **Supersedes/Superseded by** for decision evolution
