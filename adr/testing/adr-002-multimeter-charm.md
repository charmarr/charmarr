# Multimeter Test Utility Charm

**Status:** Accepted

**Related:** [adr-001-testing-strategy.md](adr-001-testing-strategy.md) — overall testing approach using pytest-bdd and Gherkin

## Context and Problem Statement

Integration testing Charmarr charms requires verifying that provider charms publish correct relation data. We need a way to test provider charms before their real consumer charms exist.

Key insight: We should never mock provider charms. When testing a requirer charm (e.g., Radarr), we use the real provider charms (charmarr-storage, Prowlarr, qBittorrent) because their provider behavior has already been validated by their own tests.

## Considered Options

* **Option 1:** Always test with real charms only (wait for consumers to exist)
* **Option 2:** Mock both provider and requirer sides
* **Option 3:** Requirer-only multimeter (test providers, use real providers for requirers)

## Decision Outcome

**Option 3 — Requirer-only multimeter charm**

charmarr-multimeter is a minimal test utility charm that:
- Implements all Charmarr interfaces as **requirer only**
- Receives relation data from provider charms under test
- Publishes minimal requirer data (instance_name) to complete the relation handshake
- Is passive — no validation, no actions, test assertions happen externally

## Testing Philosophy

```
┌─────────────────────────────────────────────────────────────────┐
│                     TESTING A PROVIDER CHARM                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐         ┌─────────────────┐                │
│  │ Provider Charm  │────────►│   Multimeter    │                │
│  │ (under test)    │ provides│ (requirer)      │                │
│  └─────────────────┘         └─────────────────┘                │
│                                      │                          │
│                              Tests read relation                │
│                              data via juju CLI/jhack            │
│                              and verify correctness             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     TESTING A REQUIRER CHARM                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐         ┌─────────────────┐                │
│  │ Real Provider   │────────►│ Requirer Charm  │                │
│  │ (already tested)│ provides│ (under test)    │                │
│  └─────────────────┘         └─────────────────┘                │
│                                      │                          │
│  Provider behavior is already        Tests verify requirer      │
│  validated - no mocking needed       handles data correctly     │
└─────────────────────────────────────────────────────────────────┘
```

**Why not mock providers?**
- Provider behavior is tested when testing the provider charm (with multimeter)
- Using real providers tests actual integration, not fake data
- Reduces maintenance burden (no fake provider logic to maintain)
- Catches real integration issues that mocks would miss

## Interface Implementation

Multimeter implements the **requirer side only** of every Charmarr interface:

| Interface | Endpoint | Requirer Data Published |
|-----------|----------|-------------------------|
| media-storage | `media-storage` | `instance_name` |
| media-indexer | `media-indexer` | `api_url`, `api_key_secret_id`, `manager`, `instance_name` |
| download-client | `download-client` | `manager`, `instance_name` |
| media-manager | `media-manager` | `requester`, `instance_name` |
| vpn-gateway | `vpn-gateway` | `instance_name` |

## Behavior

### Passive

Multimeter is entirely passive:
- Publishes minimal requirer data to complete relation handshake
- Receives provider data (stored in relation databag)
- No validation, no custom actions
- Tests use `juju show-unit` or `jhack show-relation` to inspect received data

### No Config Options

Multimeter has no config options. The requirer data it publishes uses:
- `instance_name`: The Juju app name (e.g., "charmarr-multimeter")
- Other fields: Sensible defaults or derived from app name

## Usage in Tests

```gherkin
Feature: Storage charm provides media-storage relation data

  Scenario: Storage publishes PVC details when bound
    Given charmarr-storage-k8s is deployed with storage-class backend
    And charmarr-multimeter is deployed
    When charmarr-multimeter is related to charmarr-storage-k8s via media-storage
    And the PVC becomes bound
    Then the media-storage relation should contain pvc_name "charmarr-shared-media"
    And the media-storage relation should contain mount_path "/data"
```

```python
@then('the media-storage relation should contain pvc_name "{expected}"')
def verify_relation_data(juju, expected):
    # Use juju CLI or jubilant to read relation data
    status = juju.status()
    relation_data = ...  # extract from status
    assert relation_data["pvc_name"] == expected
```

## Location

Lives in the charmarr monorepo alongside other charms:

```
charmarr/
├── charms/
│   ├── charmarr-storage-k8s/
│   ├── radarr-k8s/
│   └── charmarr-multimeter/    # test utility
└── ...
```

## Charm Structure

```
charms/charmarr-multimeter/
├── src/
│   └── charm.py          # ~50 lines - just wires up requirer interfaces
├── charmcraft.yaml       # 5 requirer endpoints
├── pyproject.toml
├── tox.ini
└── tests/
    └── unit/             # minimal tests for requirer data publishing
```

No integration tests for charmarr-multimeter — it is the integration test utility.

## Consequences

**Good:**
- Minimal implementation (~50 lines of charm code)
- No config options to maintain
- No fake provider logic to keep in sync
- Tests use real providers for requirer charms (realistic integration testing)
- Clear purpose: multimeter tests providers, real charms test requirers

**Bad:**
- Can't test requirer charms until their provider dependencies exist
- Must update multimeter when new interfaces are added

**Mitigations:**
- Epic ordering ensures providers are built before their requirers
- Interface additions are infrequent; multimeter updates are trivial (add one requirer)
