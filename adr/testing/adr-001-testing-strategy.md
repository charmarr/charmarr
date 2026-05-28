# Testing Strategy

**Status:** Accepted

**Related:** [adr-002-multimeter-charm.md](adr-002-multimeter-charm.md) — test utility charm for isolated integration testing

## Context and Problem Statement

Charmarr consists of multiple charms and shared libraries that need comprehensive testing. We need a consistent testing approach across the ecosystem that:

- Enables readable, behavior-driven integration tests
- Handles Juju model deployment via Terraform
- Shares common test utilities across charms
- Separates unit tests (fast, isolated) from integration tests (real infrastructure)

## Considered Options

### Test Framework
* **Option 1:** pytest only with custom fixtures
* **Option 2:** pytest-bdd with Gherkin syntax
* **Option 3:** pytest-operator (legacy)

### Juju Testing Library
* **Option 1:** python-libjuju directly
* **Option 2:** jubilant + pytest-jubilant
* **Option 3:** pytest-operator

### Terraform Handling
* **Option 1:** tox commands (init/apply before pytest, destroy after)
* **Option 2:** pytest fixtures (session-scoped setup/teardown)
* **Option 3:** Step definitions with TFManager wrapper

### Shared Test Code Location
* **Option 1:** Copy helpers into each charm
* **Option 2:** Separate test utilities repo
* **Option 3:** charmarr-testing package in charmarr-lib monorepo

## Decision Outcome

### Test Framework: Option 2 — pytest-bdd with Gherkin

Gherkin syntax provides readable specs that document behavior:

```gherkin
Feature: Download client relation

  Scenario: Radarr connects to qBittorrent
    Given the radarr charm is deployed
    And the qbittorrent charm is deployed
    When radarr is related to qbittorrent via download-client
    Then radarr should have qbittorrent configured as a download client
```

### Juju Testing: Option 2 — jubilant + pytest-jubilant

jubilant provides a clean API for Juju operations. pytest-jubilant integrates it with pytest.

### Terraform Handling: Option 3 — TFManager in step definitions

Terraform operations happen in Given steps, not pytest fixtures or tox commands. This keeps deployment logic with test logic and allows fine-grained control.

```python
from pytest_bdd import given
from charmarr_lib.testing import TFManager

@given("the radarr charm is deployed")
def deploy_radarr(tmp_path, juju):
    tf = TFManager(
        terraform_dir=Path(__file__).parent.parent / "terraform",
        state_file=tmp_path / "terraform.tfstate"
    )
    tf.init()
    tf.apply(env={"TF_VAR_model_name": juju.model})
```

### Shared Test Code: Option 3 — charmarr-lib-testing package

```python
from charmarr_lib.testing import TFManager, wait_for_active_idle
from charmarr_lib.testing.steps import common_deployment_steps
```

## Integration Test Structure

Per charm:

```
charms/<charm-name>/tests/integration/
├── terraform/
│   └── main.tf
├── features/
│   ├── deployment.feature
│   ├── download-client-relation.feature
│   └── reconciliation.feature
├── steps/
│   ├── common_steps.py
│   ├── deployment_steps.py
│   └── relation_steps.py
├── conftest.py
└── tests/
    ├── test_deployment.py
    ├── test_download_client_relation.py
    └── test_reconciliation.py
```

### conftest.py

Registers step definitions as pytest plugins:

```python
pytest_plugins = [
    "tests.integration.steps.common_steps",
    "tests.integration.steps.deployment_steps",
    "tests.integration.steps.relation_steps",
    "charmarr_lib.testing.steps",  # shared steps from library
]
```

### Test Files

Each test file simply imports scenarios from a feature file:

```python
# tests/test_deployment.py
from pytest_bdd import scenarios

scenarios("../features/deployment.feature")
```

All step implementations live in step modules, not test files.

### Feature File Organization

Organized by feature (capability being tested), not by scenario type:

```
features/
├── deployment.feature           # basic deploy/config
├── download-client-relation.feature
├── media-indexer-relation.feature
├── vpn-gateway-relation.feature
└── reconciliation.feature       # aggressive reconciliation behavior
```

## TFManager

Thin wrapper around terraform binary:

```python
class TFManager:
    def __init__(self, terraform_dir: Path, state_file: Path): ...
    def init(self) -> None: ...
    def apply(self, env: dict[str, str]) -> None: ...
    def output(self, output_name: str) -> str: ...
    def destroy(self) -> None: ...
```

Lives in `charmarr_lib.testing`. Supports both `terraform` and `tofu` binaries.

## Unit vs Integration Tests

| Aspect | Unit | Integration |
|--------|------|-------------|
| Location | `tests/unit/` | `tests/integration/` |
| Framework | pytest | pytest-bdd |
| Infrastructure | None (mocked) | Real Juju model |
| Speed | Fast (seconds) | Slow (minutes) |
| What's tested | Logic, models, API clients | Relations, deployment, E2E |

### Library Tests

charmarr-lib packages have unit tests only. Integration testing happens at the charm level.

```
charmarr-lib/packages/core/tests/unit/
charmarr-lib/packages/vpn/tests/unit/
charmarr-lib/packages/testing/tests/unit/
```

## tox Integration

```ini
[testenv:unit]
commands = pytest tests/unit/ {posargs}

[testenv:integration]
commands = pytest tests/integration/tests/ {posargs}
```

tox just runs pytest. Terraform handling is inside step definitions.

## Consequences

**Good:**
- Gherkin features are readable documentation
- Steps are reusable across scenarios and charms
- TFManager in steps gives fine-grained deployment control
- charmarr-testing prevents duplication across 7+ charms
- Clear separation between unit (fast) and integration (real infra)

**Bad:**
- pytest-bdd adds learning curve for contributors unfamiliar with Gherkin
- Step definitions can become verbose for complex scenarios
- Integration tests require real Juju controller and model
