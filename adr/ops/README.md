# Charmarr Operations Architecture

This directory contains the architectural decision records (ADRs) for Charmarr's CI/CD operations, automation, and developer experience tooling.

## Architecture Overview

Charmarr's operations layer provides:
- **CI Auto-Healing**: Automatic recovery from predictable CI failures using deterministic rules and LLM fallback
- **Developer Experience**: Reducing manual intervention for trivially fixable issues

## ADRs

### CI/CD Automation
- **[ADR-001: CI Auto-Healing with Parrot](adr-001-ci-auto-healing.md)** - Automatic CI failure recovery using theow rule engine with LLM fallback

## Key Design Principles

1. **Deterministic First**: Known failure patterns are handled by fast, cost-free deterministic rules before falling back to LLM
2. **Transparent Integration**: Automation wraps existing tooling (tox) without replacing it — charms are unaware of the healing layer
3. **Human-in-the-Loop**: Automated fixes are surfaced as reviewable PRs, never pushed directly
4. **Constrained Access**: LLM tools are gated per failure type — lint LLM can only touch source, test LLM can touch tests too
5. **Rule Accumulation**: Patterns discovered by LLM become deterministic rules over time, reducing costs
