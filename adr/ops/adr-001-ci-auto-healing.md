# CI Auto-Healing with Parrot

**Status:** Accepted

**Related:**
- [testing/adr-001-testing-strategy.md](../testing/adr-001-testing-strategy.md) — testing approach and tox environments
- [apps/adr-014-release-flow.md](../apps/adr-014-release-flow.md) — CI/CD architecture and centralized `.github` workflows

## Context and Problem Statement

Charmarr CI runs lint (ruff + codespell), static analysis (pyright), unit tests (pytest + coverage), and integration tests (pytest-bdd + jubilant) for each charm on every PR and publish. Failures fall into predictable categories:

- **Transient**: network timeouts, rate limits, infrastructure flakiness — just need a retry
- **Lint**: ruff violations and codespell typos — most are auto-fixable
- **Static typing**: pyright errors — some follow patterns, many are contextual
- **Unit test failures**: code or test logic is wrong — requires understanding intent
- **Integration test failures**: infrastructure-dependent, BDD scenario failures against live Juju models

Currently all failures require manual developer intervention, even trivially fixable ones like a missing `ruff --fix`. For integration tests, developers often SSH into runners or use slow tmux sessions to diagnose failures on live models. This creates unnecessary friction and slows development.

[theow](https://github.com/adhityaravi/theow) is a programmable rule engine with an inbuilt LLM agent designed for automatic failure recovery. It matches failures against deterministic rules first (fast, no LLM cost) and falls back to LLM-powered investigation when no rule matches. Rules accumulate over time, reducing LLM usage toward zero as failure modes are finite.

## Considered Options

### Rule Engine
* **Option 1:** Custom retry/fix scripts in GitHub Actions
* **Option 2:** theow rule engine with LLM fallback

### Integration Mode
* **Option 1:** theow CLI mode — `theow run tox -e lint`
* **Option 2:** Python API — `@parrot.mark()` decorators wrapping tox calls

### Location
* **Option 1:** Parrot in `.github` repo (centralized with CI)
* **Option 2:** Parrot in `charmarr` monorepo (alongside charm code)
* **Option 3:** Parrot as its own repo

### Recovery Granularity
* **Option 1:** Tox-level for all collections
* **Option 2:** Per-test for all collections
* **Option 3:** Hybrid — tox-level for lint/static/unit, per-test for integration

### Fix Delivery
* **Option 1:** Direct push to feature branch, CI passes
* **Option 2:** Create fix PR against feature branch, CI always fails, PR merge heals

## Decision Outcome

### Rule Engine: Option 2 — theow

**Rationale:**
- Deterministic rules handle known patterns without LLM cost
- LLM rules handle novel failures with tool-gated access
- Rules can have deterministic actions (run a command) or LLM-powered actions (investigate and fix with a prompt + constrained tools)
- Battle-tested in sd-tools for automatic pipeline recovery
- Rule accumulation means LLM costs decrease over time toward zero

### Integration Mode: Option 2 — Python API

**Rationale:**
- Rich context extraction via `context_from` lambdas
- Lifecycle hooks (setup/teardown) for workspace checkpoint and recovery
- Two-layer tool gating: instance-level registration + per-rule whitelisting in `llm_config.tools`
- Tox remains the underlying test runner — parrot wraps it, doesn't replace it

### Location: Option 3 — Own repo

**Rationale:**
- Parrot is a theow runtime, not a package — it's a standalone repo (`charmarr/parrot/`) that owns its rules, actions, prompts, and vector store
- Central theow runtime for the entire charmarr org — all charms heal through one rule set
- Self-pushing: when an ephemeral rule successfully heals a failure, it gets promoted and parrot pushes the new rule into its own repo. This creates an unsupervised agentic repo that accumulates healing knowledge over time
- Clean separation from charm code — parrot evolves independently
- CI checks out parrot alongside the charm repo when needed

### Recovery Granularity: Option 1 — Tox-level for all

**Rationale:**
- lint, static, and unit cannot be function-level — they're whole-tool invocations
- Integration tests appear per-test, but CI already parallelizes them: `charm-publish.yaml` discovers `test_*.py` files and creates a matrix with one test file per runner (`fail-fast: false`). Each runner executes `uvx tox -e integration -- -k "${{ matrix.suite }}"`. So each runner's tox invocation IS one test file — tox-level and per-test-file are the same thing
- Every mark point wraps a single tox call. No attempt differentiation between collections.

| CI Stage | Parrot Wraps | Notes |
|----------|-------------|-------|
| lint | `tox -e lint` | PR CI |
| static | `tox -e static` | PR CI |
| unit | `tox -e unit` | PR CI |
| itest | `tox -e integration -- -k "test_foo.py" --keep-models --model parrot-<charm>-<suite>` | Publish CI only |

### Fix Delivery: Option 2 — PR-based, CI always fails

**Rationale:**
- Cannot push directly to the feature branch — changes must be persisted and reviewed
- theow v0.0.20 `suppress_exc` feature: teardown sets `state["suppress_exc"] = False` before raising, which makes the teardown exception propagate instead of being swallowed. This means CI always fails even when theow heals the function
- The teardown creates a fix PR before raising, so the developer sees the fix PR alongside the failed CI run
- When the fix PR is merged into the feature branch, CI re-runs and naturally passes
- Both deterministic and LLM fixes follow this same PR flow
- Worst case is a bad PR that gets closed — human always reviews before merge

## Implementation Details

### Theow Instance

```python
from pathlib import Path
from theow import Theow

_parrot_dir = Path(__file__).parent

parrot = Theow(
    theow_dir=_parrot_dir,
    name="Parrot",
    llm="copilot/gpt-5.3-codex",
    llm_secondary="copilot/claude-opus-4-6",
    session_limit=10,
    max_tool_calls_per_session=60,
    max_tokens_per_session=200000,
    archive_llm_attempt=True,
)
```

LLM provider: GitHub Copilot gateway (free with Copilot subscription). `GITHUB_TOKEN` env var for both LLM API access and PR creation via `gh` CLI.

### Module Structure

Follows the sd-tools pattern:

```
parrot/                         # own repo, not a package
├── .gitignore                  # ignores chroma/
├── pyproject.toml              # theow>=0.0.20, Python >=3.12,<3.14
├── __init__.py                 # re-exports parrot instance, triggers tool registration
├── __main__.py                 # CLI: python -m parrot <collection> --charm-path ...
├── _engine.py                  # Theow instance + setup/teardown hooks
├── _runner.py                  # @parrot.mark() wrapped tox calls per collection
├── _tools.py                   # all LLM tools (file, command, juju, git, PR)
├── rules/                      # deterministic + LLM rule YAML files
├── actions/                    # deterministic action Python files
├── prompts/                    # LLM prompt templates
└── chroma/                     # vector DB (gitignored, auto-managed by theow)
```

- `__init__.py` imports `parrot` from `_engine` and imports `_tools` to trigger tool registration (side-effect import)
- `_tools.py` contains ALL tools — no separate PR module
- `rules/`, `actions/`, `prompts/` are auto-created by theow — no `.gitkeep` files needed
- Only `chroma/` is gitignored — the user decides whether to keep ephemeral/failed/observations

### Python Version Constraint

`>=3.12,<3.14` — chromadb (theow's vector store dependency) is incompatible with Python 3.14.

### Two-Layer Tool Architecture

Following the sd-tools pattern, tools are registered at two layers:

**Layer 1 — Instance-level registration** (`_tools.py`): All tools are registered on the parrot instance via `parrot.tool()`. This includes both unrestricted tools (for deterministic actions) and restricted tools (for LLM use).

**Layer 2 — Rule-level whitelisting** (`llm_config.tools` in rule YAML): Each LLM rule declares a whitelist of only the tools that rule's LLM invocation can use. Unrestricted generic tools (`write_file`, `run_command`) are registered on the instance but never appear in any LLM rule's tool list — they exist for deterministic actions only.

Each restricted tool embeds its own guardrails (file suffix allowlists, command prefix allowlists), providing defense-in-depth even within the tool itself.

**Instance-level tools:**

| Tool | Type | Purpose |
|------|------|---------|
| `read_file` | unrestricted | read any file in charm directory |
| `write_file` | unrestricted | write any file (deterministic actions only) |
| `list_directory` | unrestricted | list directory contents |
| `run_command` | unrestricted | run any command (deterministic actions only) |
| `write_charm_file` | restricted | write files with prompt-guided guardrails for LLM |
| `run_lint_cmd` | restricted | allowlist: ruff, codespell |
| `run_static_cmd` | restricted | allowlist: pyright |
| `run_test_cmd` | restricted | allowlist: pytest, coverage |
| `run_juju_cmd` | restricted | any juju command, model flag auto-injected |
| `run_kubectl_cmd` | restricted | any kubectl command |
| `pack_charm` | restricted | charmcraft pack to separate path (not overwriting CI's `$CHARM_PATH`) |
| `retry_test` | restricted | re-run the test to check if failure is transient |
| `git_diff` | restricted | show current workspace changes |

**Per-rule tool assignments (LLM rules):**

| Rule | Tools Given to LLM |
|------|-------------------|
| lint LLM | `read_file`, `write_charm_file`, `run_lint_cmd`, `list_directory`, `git_diff` |
| static LLM | `read_file`, `write_charm_file`, `run_static_cmd`, `list_directory`, `git_diff` |
| unit LLM | `read_file`, `write_charm_file`, `run_test_cmd`, `list_directory`, `git_diff` |
| itest LLM | `read_file`, `write_charm_file`, `run_test_cmd`, `run_juju_cmd`, `run_kubectl_cmd`, `pack_charm`, `retry_test`, `list_directory`, `git_diff` |

### pack_charm Tool — Separate Build Path

The `pack_charm` tool that the LLM uses during investigation packs the charm to a **separate path** (e.g., `parrot-build/`), NOT overwriting the CI's pre-packed `.charm` file at `$CHARM_PATH`. This is critical because `$CHARM_PATH` is the clean checkpoint that setup uses to refresh the deployed charm back to the feature branch state between retry attempts.

### retry_test Tool — Transient Failure Detection

The `retry_test` tool allows the LLM to re-run the test against the existing pre-deployed model before starting investigation. In a pre-deployed model, the test assertions take ~1-2 minutes (deploy steps are skipped due to idempotency). This is a cheap check to rule out transient failures before the LLM burns tokens investigating. The prompt should encourage: "first retry the test to rule out transient failures before investigating."

### itest Juju/Kubectl Tools — Unrestricted Commands

For integration tests, `run_juju_cmd` and `run_kubectl_cmd` allow any juju or kubectl command respectively. The LLM is investigating a test model on a CI runner — restricting to specific subcommands is unnecessarily limiting. Even if the LLM does something destructive, it's a test model, not production. The model flag is auto-injected by `run_juju_cmd` to prevent the LLM from accidentally targeting the wrong model.

### Setup and Teardown Hooks

Following the sd-tools stash pattern. Setup checkpoints the workspace, teardown either keeps changes (success) or restores the checkpoint (failure). Same logic every attempt — no `if attempt > 1` branching.

**Setup (all collections):**

```python
def setup(state, attempt):
    charm_path = state["charm_path"]
    git = Git(charm_path)
    state["_stash_created"] = git.stash_push(
        message="parrot-recovery", include_untracked=True
    )
    if state["_stash_created"]:
        git.stash_apply()
    return state
```

1. `git stash push` — checkpoint the clean workspace (includes untracked files)
2. `git stash apply` — restore the working copy so the LLM works on it
3. The stash is the savepoint. The working copy is the workspace.

**Setup (itest additional):**

```python
    # Reset deployed charm to clean CI build
    juju_refresh(state["model_name"], state["app_name"], os.environ["CHARM_PATH"])
```

For integration tests, setup also refreshes the deployed app with the clean pre-packed charm from CI (`$CHARM_PATH`). This resets the deployed charm state so the LLM's previous attempt's pack+refresh doesn't pollute the next attempt.

**Teardown (all collections):**

```python
def teardown(state, attempt, success):
    charm_path = state["charm_path"]
    git = Git(charm_path)

    if success:
        # Keep LLM's changes, drop the savepoint
        if state.get("_stash_created"):
            git.stash_drop()
        # Create fix PR
        pr_url = create_fix_pr(git, state)
        # Fail CI — PR merge heals
        state["suppress_exc"] = False
        raise ParrotHealed(f"Fixed by parrot. PR: {pr_url}")
    else:
        # Discard LLM's changes, restore clean workspace
        git.reset_working_tree()
        if state.get("_stash_created"):
            git.stash_pop()
        # Post observations on last attempt
        if attempt == state.get("max_retries"):
            post_observations(state)
```

**Success path:**
1. `git stash drop` — discard the savepoint (LLM's changes are the desired state)
2. Create a fix branch, commit changes, push, create PR against the feature branch
3. Set `state["suppress_exc"] = False` — theow v0.0.20 feature that makes the teardown exception propagate instead of being swallowed
4. Raise `ParrotHealed` — CI fails with a clear message pointing to the fix PR

**Failure path:**
1. `git reset_working_tree` — discard all of the LLM's changes
2. `git stash pop` — restore the clean checkpoint
3. On the last attempt: post the LLM's observations/analysis as a comment on the triggering PR. Even failed investigations are valuable — they prevent developers from needing slow tmux sessions to diagnose the same issue

### CI Architecture Context

**PR CI** (`charm-ci.yaml`) — runs on every PR, 4 parallel jobs:
- `lint` → `uvx tox -e lint`
- `static` → `uvx tox -e static`
- `unit` → `uvx tox -e unit`
- `terraform-validate` → validates terraform modules

No integration tests on PRs. Parrot replaces the tox invocations for lint, static, and unit.

**Publish CI** (`charm-publish.yaml`) — runs on push to main:
1. `build` — packs the charm via `charmcraft pack`, uploads `.charm` as artifact
2. `integration-matrix` — discovers `test_*.py` files: `find tests/integration -name 'test_*.py' -printf '%f\n'` → outputs JSON array
3. `integration` — matrix strategy with `fail-fast: false`, one runner per test file. Downloads pre-packed charm artifact. Sets `CHARM_PATH` env var to the `.charm` file path. Command: `uvx tox -e integration -- -k "${{ matrix.suite }}"`
4. `publish` — publishes to Charmhub after all tests pass

Parrot replaces the tox invocation in the integration job. The pre-packed `.charm` from the build job is available via `$CHARM_PATH`.

### Integration Test Model Management

**Deterministic model name:** The marked function generates a deterministic model name (`parrot-<charm>-<suite>`) and passes `--model` and `--keep-models` to tox. This ensures:
- The model name is known to parrot for LLM investigation tools (auto-injected into `run_juju_cmd`)
- The model persists across retries (`--keep-models`)
- Setup can refresh the deployed charm between attempts

**Deploy idempotency:** All deployment steps in charmarr-lib-testing and charm conftest.py fixtures are already idempotent. Every deploy fixture guards with `if "app_name" in status.apps: return` before calling `juju.deploy()`. All relation steps use `ensure_related()` which checks `if endpoint in app_status.relations: return`. This means re-running tox against an existing model safely skips all deployment and proceeds directly to test assertions.

This idempotency is implemented at two levels:
1. **conftest.py fixtures** — all `*_deployed` fixtures (every charm) check `status.apps` before deploying
2. **Shared BDD steps** — all `@given` deployment steps in `charmarr_lib.testing.steps.*` (storage, multimeter, gluetun, mesh, arr) check `status.apps` before deploying

Lower-level helpers (`deploy_arr_charm()`, `deploy_multimeter()`, `create_vpn_secret()`) are NOT individually idempotent, but all callers guard them.

### Integration Test Live Investigation

For integration test failures, the LLM has live access to the running Juju model via `run_juju_cmd` and `run_kubectl_cmd`. This enables investigation that would otherwise require a developer to SSH into the runner:

- `juju status` — see application and unit states
- `juju debug-log` — read charm logs for error context
- `kubectl get pods` — check pod states and restarts
- `kubectl logs` — read container logs
- `juju config` — inspect application configuration
- Any other juju/kubectl command the LLM deems necessary

The LLM can also `pack_charm` (to a separate build path) and use `run_juju_cmd` to `juju refresh` the app with its fix to test it on the live model before the formal retry.

**Even when the LLM fails to fix the issue**, its observations are posted as a PR comment. This captures diagnostic information (juju status output, log excerpts, error analysis) that saves developers from having to reproduce the failure and investigate manually.

### Recovery Flow

```
1. CI triggers (PR or publish)
2. python -m parrot <collection> --charm-path <path>
3. Internally runs: tox -e <env> [itest flags]
4. Tox succeeds → exit 0 (transparent pass-through, <1s overhead)
5. Tox fails → @parrot.mark catches exception
   a. Setup: git stash push + apply (checkpoint workspace)
      For itest: also juju refresh from $CHARM_PATH (reset charm)
   b. Rule engine resolves:
      - Deterministic rule matches? → execute action
      - No match, LLM rule matches? → LLM investigates with gated tools
      - No match, explorable? → LLM explores, writes ephemeral rule
   c. Retry tox
   d. Teardown:
      - Success → stash drop, create fix PR, suppress_exc=False, raise
      - Failure → reset working tree, stash pop, (last attempt: post observations)
   e. Loop up to max_retries per depth level, max_depth error transitions
6. All attempts exhausted → post observations as PR comment, exit 1
7. Fix PR merged → CI re-runs, tox passes naturally
```

### Self-Pushing Rules

When an ephemeral rule (written by the LLM during exploration) successfully heals a failure, theow promotes it to the main `rules/` directory. Parrot then pushes the new rule into its own repo. This creates an unsupervised agentic workflow where:

- The LLM discovers a fix for a novel failure
- The fix is validated by theow's retry mechanism
- The rule is promoted and pushed to the parrot repo
- Next time the same failure pattern occurs, the deterministic rule handles it instantly — no LLM needed

Over time, as rules accumulate and failure modes are finite, LLM invocations trend toward zero.

### Mark Configuration

| Collection | explorable | tags | max_retries | max_depth | allow_escalation |
|-----------|-----------|------|-------------|-----------|-----------------|
| lint | Yes | [lint, ruff, codespell] | 3 | 2 | Yes |
| static | Yes | [static, pyright] | 3 | 2 | Yes |
| unit | Yes | [unit, pytest] | 3 | 3 | Yes |
| itest | Yes | [itest, integration, juju] | 3 | 2 | Yes |

All collections are explorable — novel patterns can become deterministic rules for any collection.

### Deterministic Rules

**Lint:**
- `ruff_autofix` — when stderr contains ruff violations → action: `ruff check --fix && ruff format`
- `codespell_fix` — when stderr contains codespell misspelling → action: `codespell --write-changes`

**All collections:**
- `transient_retry` — when stderr matches transient patterns (timeout, rate limit, connection refused, resource unavailable) → action: no-op (theow retries the function automatically)

### LLM Rules

Each LLM rule specifies a prompt template and a tool whitelist:

**`lint_llm`:**
- Catch-all for lint failures not fixed by deterministic rules
- `llm_config.tools`: `[read_file, write_charm_file, run_lint_cmd, list_directory, git_diff]`
- Prompt: read the offending file, fix the issue, re-run lint to verify

**`static_llm`:**
- Pyright type errors
- `llm_config.tools`: `[read_file, write_charm_file, run_static_cmd, list_directory, git_diff]`
- Prompt: read the file at reported line, understand the type error, fix annotations

**`unit_llm`:**
- Pytest failures
- `llm_config.tools`: `[read_file, write_charm_file, run_test_cmd, list_directory, git_diff]`
- Prompt: understand whether source or test is wrong, fix the right one, re-run to verify

**`itest_llm`:**
- Integration test BDD scenario failures
- `llm_config.tools`: `[read_file, write_charm_file, run_test_cmd, run_juju_cmd, run_kubectl_cmd, pack_charm, retry_test, list_directory, git_diff]`
- Prompt: first retry to rule out transient failure, then investigate live model, diagnose root cause, fix code and/or charm, verify

### CI Integration

In `.github` centralized workflows:

**`charm-ci.yaml`** (PR CI):
```yaml
# Before
- run: uvx tox -e lint
  working-directory: ${{ inputs.charm-path }}

# After
- run: uv run --project ${{ github.workspace }}/parrot python -m parrot lint --charm-path ${{ inputs.charm-path }}
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    THEOW_EXPLORE: "1"
```

Same pattern for static and unit.

**`charm-publish.yaml`** (publish CI, integration job):
```yaml
# Before
- run: uvx tox -e integration -- -k "${{ matrix.suite }}"
  working-directory: ${{ inputs.charm-path }}

# After
- run: uv run --project ${{ github.workspace }}/parrot python -m parrot itest --charm-path ${{ inputs.charm-path }} --suite "${{ matrix.suite }}"
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    CHARM_PATH: ${{ env.CHARM_PATH }}
    THEOW_EXPLORE: "1"
```

### Environment Variables

| Variable | Purpose | Source |
|----------|---------|-------|
| `GITHUB_TOKEN` | Copilot LLM API access + PR creation via `gh` CLI | GitHub Actions secret (already available) |
| `THEOW_EXPLORE` | Enable/disable LLM exploration (set to "1" to enable) | Set in CI workflow |
| `CHARM_PATH` | Path to pre-packed `.charm` file (itest only) | Set by publish CI build job |

No additional secrets needed — GitHub Copilot uses the existing `GITHUB_TOKEN`.

### Human-in-the-Loop Safety

The maximum action parrot can take is creating a PR or posting a comment. It cannot:
- Push directly to the feature branch (creates a fix PR instead)
- Merge anything
- Modify CI configuration
- Access secrets beyond its GitHub token
- Affect production infrastructure (itest models are ephemeral CI models)

Every fix is reviewable by a human before merge. Even the LLM's investigation tools are bounded — `run_juju_cmd` auto-injects the model flag to prevent targeting wrong models, and `pack_charm` writes to a separate path to protect the CI artifact.

## Consequences

### Good

- Trivial failures (ruff, codespell, transient) resolved automatically without developer intervention
- Non-trivial failures get LLM-powered fix attempts surfaced as reviewable PRs
- Unresolvable failures get diagnostic analysis posted as PR comments — developer gets a head start on debugging instead of slow tmux sessions
- Integration test live investigation gives the LLM the same diagnostic capabilities a developer would have on the runner
- Deterministic rules handle known patterns instantly (no LLM cost, milliseconds)
- Rule accumulation: LLM-discovered patterns become deterministic rules, LLM costs trend toward zero
- Self-pushing rules create an unsupervised agentic repo that accumulates healing knowledge
- Transparent integration: charms don't know parrot exists, tox remains the test runner
- Deploy idempotency already handled — no changes needed to charmarr-lib-testing
- Pre-packed charm from CI means no expensive `charmcraft pack` during recovery
- Workspace checkpointing via git stash ensures each retry attempt starts clean
- Human-in-the-loop: worst case is a bad PR that gets closed

### Bad

- LLM API costs for non-trivial failures (mitigated by Copilot gateway being free with subscription and deterministic rules handling common cases)
- Additional complexity in CI pipeline
- LLM fixes may be wrong and waste reviewer time
- Integration test retry adds ~1-2 minutes per attempt (deploy steps skipped, assertions only)
- `pack_charm` during LLM investigation adds overhead when the LLM modifies charm code

### Neutral

- CI always fails when parrot heals — by design, forces PR review before changes land
- Ephemeral rules that heal get promoted and pushed to parrot repo automatically
- Switching LLM providers is a config change in `_engine.py`
- Fix PRs create additional PR noise, but each represents an attempted resolution
- Python version pinned to `<3.14` due to chromadb — will be lifted when chromadb supports 3.14

## Related ADRs

- [testing/adr-001-testing-strategy](../testing/adr-001-testing-strategy.md) — testing approach and tox environments that parrot wraps
- [apps/adr-014-release-flow](../apps/adr-014-release-flow.md) — CI/CD architecture and centralized `.github` workflows where parrot integrates
