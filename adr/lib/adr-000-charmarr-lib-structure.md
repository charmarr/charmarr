# Charmarr-Lib Monorepo Structur# Charmarr-Lib Monorepo Structure

**Status:** Accepted

## Context and Problem Statement

Charmarr requires three shared libraries: `charmarr-lib-core` (interfaces, API clients, reconcilers for arr applications), `charmarr-lib-vpn` (VPN gateway interface and StatefulSet patching), and `charmarr-lib-testing` (testing utilities and pytest-bdd steps). How should these libraries be organized for development, packaging, and distribution?

Key considerations:
- Clean, consistent public API across packages
- Independent installability (`pip install charmarr-lib-core` vs `pip install charmarr-lib-vpn`)
- Shared `charmarr_lib` namespace for discoverability
- Freedom to reorganize internals without breaking consumers
- `charmarr-lib-vpn` should remain reusable outside Charmarr ecosystem

## Considered Options

* **Option 1: Separate repositories** — `github.com/adi/charmarr-core` and `github.com/adi/charmarr-vpn`
* **Option 2: Monorepo with separate namespace packages** — single repo, two pip-installable packages under `charmarr.*` namespace
* **Option 3: Single package with extras** — `pip install charmarr-lib[vpn]`

## Decision Outcome

Chosen option: **Option 2 (Monorepo with namespace packages)**, because it provides development convenience while maintaining distribution flexibility and clear naming.

### Repository Structure

```
github.com/adi/charmarr-lib/
├── core/                       # At root level, not nested
│   ├── pyproject.toml
│   └── src/
│       └── charmarr_lib/       # Underscore for Python module names
│           └── core/
│               ├── __init__.py
│               ├── interfaces/
│               │   ├── __init__.py
│               │   ├── _media_indexer.py
│               │   ├── _download_client.py
│               │   ├── _media_manager.py
│               │   ├── _media_storage.py
│               │   └── _media_server.py
│               ├── _clients/
│               │   ├── _base.py
│               │   ├── _arr.py
│               │   ├── _prowlarr.py
│               │   ├── _plex.py
│               │   └── _overseerr.py
│               ├── _reconcilers/
│               │   ├── _download_clients.py
│               │   ├── _root_folders.py
│               │   └── _applications.py
│               └── _models/
│                   └── _config_builders.py
│
├── vpn/
│   ├── pyproject.toml
│   └── src/
│       └── charmarr_lib/
│           └── vpn/
│               ├── __init__.py
│               ├── interfaces/
│               │   ├── __init__.py
│               │   └── _gateway.py
│               ├── _patching/
│               │   ├── _models.py
│               │   ├── _gateway.py
│               │   ├── _client.py
│               │   └── _network_policy.py
│               └── _constants.py
│
└── testing/
    ├── pyproject.toml
    └── src/
        └── charmarr_lib/
            └── testing/
                ├── __init__.py
                └── _fixtures.py
```

### Installation

```bash
pip install charmarr-lib-core
pip install charmarr-lib-vpn
pip install charmarr-lib-testing
```

### Public API

Two import paths per package — `interfaces` for relation classes/models, root for everything else:

```python
# Core
from charmarr_lib.core.interfaces import (
    MediaIndexerProvider,
    MediaIndexerRequirer,
    MediaIndexerProviderData,
    DownloadClientProvider,
    DownloadClientRequirer,
    DownloadClientProviderData,
    # ...
)
from charmarr_lib.core import (
    ArrApiClient,
    ProwlarrApiClient,
    reconcile_download_clients,
    reconcile_root_folder,
    # ...
)

# VPN
from charmarr_lib.vpn.interfaces import (
    VPNGatewayProvider,
    VPNGatewayRequirer,
    VPNGatewayProviderData,
    VPNGatewayRequirerData,
)
from charmarr_lib.vpn import (
    patch_gateway_statefulset,
    patch_client_statefulset,
    create_killswitch_network_policy,
    # ...
)

# Testing
from charmarr_lib.testing import (
    TFManager,
    # pytest-bdd step definitions
    # test fixtures
    # ...
)
```

### Conventions

1. **Namespace packages** — `charmarr_lib` as shared namespace, with `__init__.py` in subpackages
2. **Underscore naming** — Python module names use underscores (`charmarr_lib`), package names use hyphens (`charmarr-lib-core`)
3. **Underscore-prefixed internals** — all implementation files and directories prefixed with `_`
4. **Re-export via `__init__.py`** — public API defined explicitly in `__init__.py` files
5. **Consistent structure** — all packages follow same pattern (`interfaces/` + everything else)

### pyproject.toml

**Root pyproject.toml:**
```toml
[tool.uv]
package = false  # This is a workspace, not a package

[tool.uv.workspace]
members = ["core", "vpn", "testing"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "pyright>=1.1.350",
    "tox>=4.0",
]
```

**core/pyproject.toml:**
```toml
[project]
name = "charmarr-lib-core"
description = "Core charm libraries for Charmarr media automation"
dynamic = ["version"]
dependencies = [
    "ops>=2.0",
    "pydantic>=2.0",
    "lightkube>=0.15",
    "httpx>=0.27",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/charmarr_lib"]

[tool.hatch.version]
path = "src/charmarr_lib/core/_version.py"
```

**vpn/pyproject.toml:**
```toml
[project]
name = "charmarr-lib-vpn"
description = "VPN gateway charm library for Kubernetes"
dynamic = ["version"]
dependencies = [
    "ops>=2.0",
    "pydantic>=2.0",
    "lightkube>=0.15",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/charmarr_lib"]

[tool.hatch.version]
path = "src/charmarr_lib/vpn/_version.py"
```

### Testing Strategy

**Library repo: unit tests only.** The library produces data structures and implements decision logic — unit tests verify correctness. No real K8s or Juju integration happens within the library itself.

**Charm repo: unit + integration tests.** Charms test against real infrastructure using pytest-operator / jubilant. Integration tests are the source of truth — if unit tests pass but integration fails, the mock was wrong. The `charmarr-lib-testing` package provides shared fixtures and pytest-bdd step definitions.

```
core/
├── tests/
│   └── unit/
│       ├── interfaces/
│       │   └── test_media_indexer.py
│       ├── clients/
│       │   └── test_arr.py
│       └── reconcilers/
│           └── test_download_clients.py
│
vpn/
├── tests/
│   └── unit/
│       ├── interfaces/
│       │   └── test_gateway.py
│       └── patching/
│           ├── test_gateway_patch.py
│           └── test_client_patch.py
│
testing/
└── tests/
    └── unit/
        └── test_fixtures.py
```

**Focus unit tests on:**
- Reconciler decision logic (add/update/delete)
- K8s patch generation (easy to mess up specs)
- Pydantic model validation

**Skip:**
- Trivial re-exports
- `__init__.py` wiring

### Consequences

**Good:**
- Single repo for coordinated development, PRs can span all packages
- Independent versioning and releases when needed
- Clear `charmarr_lib.*` namespace signals ecosystem membership
- Underscore convention prevents accidental imports of internals
- `charmarr-lib-vpn` has no dependency on `charmarr-lib-core`, remains independently reusable
- Consistent import patterns reduce cognitive load
- Root-level packages simplify structure (no nested `packages/` directory)

**Bad:**
- Namespace packages with hatchling require specific configuration (`packages = ["src/charmarr_lib"]`)
- Three `pyproject.toml` files to maintain (plus root workspace config)
- Local development requires editable installs of all packages
- Module names (`charmarr_lib`) differ from package names (`charmarr-lib-core`)
