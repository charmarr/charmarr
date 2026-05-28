# Reconciliation Philosophy: When to Respect vs Override User Configuration

## Context and Problem Statement

Charmarr charms reconcile application configuration via API calls to sync the application state with the desired state defined by Juju relations and charm config. However, applications also expose web UIs where users can manually configure settings. When charm reconciliation and manual user configuration conflict, the charm must decide whether to:

1. **Override** user changes to enforce Juju-defined state (aggressive reconciliation)
2. **Preserve** user changes and only fill in missing configuration (respectful reconciliation)
3. **Detect and sync** user changes back to Juju state (self-healing)

This decision affects user experience, operational predictability, and the "charm vs web UI" authority model. We need a consistent philosophy across all Charmarr charms that balances automation with user control.

## Decision Drivers

* **Predictability**: Users should know what will happen when they change settings via web UI
* **Infrastructure as Code**: Juju topology should be source of truth for infrastructure connections
* **User Autonomy**: Users should control preferences about content quality and organization
* **Self-Healing**: Common user actions (credential rotation) shouldn't break integrations
* **Documentation Clarity**: Behavior should be easy to explain and understand

## Considered Options

* **Option A**: Always aggressive - override all user changes
* **Option B**: Always respectful - never override user changes
* **Option C**: Category-based approach - aggressive for infrastructure, respectful for preferences

## Decision Outcome

Chosen option: **"Option C: Category-based approach"**, because it provides the right balance between automation and user control. Different types of configuration have different authority models, and applying the same reconciliation strategy to all configuration would either break automation (option B) or prevent all customization (option A).

## Configuration Categories

### Category 1: Infrastructure Integration (Aggressive Reconciliation)

**Examples**: Download clients, indexers, root folders, external URLs

**Reconciliation Strategy**: **AGGRESSIVE** - Charmarr owns this configuration completely.

**Behavior**:
- Charm reconciles to match Juju relations exactly
- Any configuration not defined in Juju relations is DELETED
- Manual web UI changes are OVERWRITTEN on next reconcile
- Users CANNOT add items via web UI that persist

**Rationale**:
- These represent infrastructure topology that should match Juju model
- Allowing manual additions creates "hidden state" outside IaC
- Users should use `juju relate` to add connections, not web UI
- Drift between Juju and application state causes operational confusion

**Example - Download Clients in Radarr**:
```python
def reconcile_download_clients(
    api_client: ArrApiClient,
    desired_clients: list[DownloadClientProviderData],
    category: str,
    model: Model,
) -> None:
    """Reconcile download clients to match desired state from relations.

    IMPORTANT: This is aggressive reconciliation. Any download client
    not in desired_clients will be DELETED, including manually-configured
    clients added via the web UI.
    """
    current = api_client.get("/downloadclient")
    current_names = {dc["name"] for dc in current}
    desired_names = {dc.instance_name for dc in desired_clients}

    # Delete anything not in desired state
    for name in current_names - desired_names:
        api_client.delete_by_name("/downloadclient", name)

    # Add/update desired state
    for client in desired_clients:
        api_client.create_or_update("/downloadclient", client)
```

**User Communication**: Clearly document in charm README and web UI tooltips (if possible) that this configuration is managed by Juju and web UI changes will be lost.

---

### Category 2: User Preferences (Respectful Reconciliation)

**Examples**: Quality profiles, default servers, UI preferences, category paths

**Reconciliation Strategy**: **RESPECTFUL** - Charmarr suggests defaults, user has final say.

**Behavior**:
- Charm provides sensible defaults on first run
- Charm checks if user has customized settings before changing them
- Manual web UI changes are PRESERVED
- Charm only fills in missing configuration, never overwrites existing

**Rationale**:
- These are subjective user choices about content quality and organization
- Users expect to customize these via familiar web UI
- Overwriting would frustrate users and remove value of web UI
- Defaults should be helpful, not mandatory

**Example - Quality Profiles in Overseerr**:
```python
def _configure_radarr_server(self, provider: MediaManagerProviderData):
    """Configure Radarr server in Overseerr with respectful reconciliation."""

    # Get existing configuration
    existing_servers = self._api_call("GET", "/api/v1/settings/radarr")
    existing_server = next(
        (s for s in existing_servers if s['name'] == provider.instance_name),
        None
    )

    # Determine profile - RESPECT existing user choice
    if existing_server and existing_server.get('activeProfileId'):
        profile_id = existing_server['activeProfileId']  # User's choice
    else:
        profile_id = provider.quality_profiles[0].id  # Sensible default

    # Configure with preserved user preference
    self._api_call("PUT", f"/api/v1/settings/radarr/{existing_server['id']}", {
        "activeProfileId": profile_id,  # User choice preserved
        # ... other fields updated from relation data ...
    })
```

**User Communication**: Document that defaults are provided, but users can customize freely via web UI.

---

### Category 3: Credentials (Self-Healing Reconciliation)

**Examples**: API keys, passwords, authentication tokens

**Reconciliation Strategy**: **SELF-HEALING** - Detect drift and sync changes back to Juju.

**Behavior**:
- Charm reads credentials from application config
- Charm detects when credentials differ from Juju secret (drift)
- Charm updates Juju secret to match application state
- Related charms receive secret-changed event and update automatically
- Brief window (up to 5 minutes) where credentials are out of sync

**Rationale**:
- Users WILL rotate credentials via familiar web UI despite documentation
- Blocking rotation via web UI frustrates users
- Self-healing is better than requiring manual Juju secret updates
- 5-minute drift window is acceptable for homelab use cases

**Example - API Key Drift Detection**:
```python
def _on_update_status(self, event):
    """Detect credential drift and auto-reconcile."""

    # Read current state from config
    current_key = self._read_api_key_from_config()

    # Read stored state from secret
    secret = self.model.get_secret(label="app-api-key")
    stored_key = secret.get_content()["api-key"]

    # Drift detected?
    if current_key != stored_key:
        logger.warning("Credential drift detected - syncing secret to match config")
        secret.set_content({"api-key": current_key})
        # Triggers secret-changed on all observers - they update automatically
        self.unit.status = ActiveStatus("Running (credentials auto-synced)")
```

**User Communication**: Document that web UI rotation is supported with up to 5-minute propagation delay.

---

## Decision Matrix

| Configuration Type | Example | Strategy | Manual Changes | Juju Authority |
|-------------------|---------|----------|----------------|----------------|
| Infrastructure connections | Download clients, indexers | **Aggressive** | Deleted | 100% |
| Structural config | Root folders, external URLs | **Aggressive** | Overwritten | 100% |
| User preferences | Quality profiles, defaults | **Respectful** | Preserved | Defaults only |
| UI customization | Category names, paths | **Respectful** | Preserved | Suggestions |
| Credentials | API keys, passwords | **Self-healing** | Synced to Juju | Bidirectional |

## Implementation Guidelines

### For Charm Developers

When implementing reconciliation logic, determine category:

1. **Is this infrastructure topology?** → Aggressive
2. **Is this user preference/organization?** → Respectful
3. **Is this a credential?** → Self-healing

### Documentation Requirements

Each charm README should include:

```markdown
## Configuration Management

Charmarr manages different types of configuration differently:

### Managed by Juju (Do not edit in web UI)
- Download clients - Use `juju relate` to add clients
- Indexers - Use `juju relate` to add Prowlarr
- Root folders - Configured via charm settings

Any manual changes to these will be overwritten.

### Suggested Defaults (Customize freely)
- Quality profiles - Defaults from Trash Guides, customize as needed
- Category paths - Sensible defaults provided
- Default servers - First-related server is default

Your web UI changes to these are preserved.

### Credentials (Supports web UI rotation)
- API keys - Can be rotated via web UI
- Passwords - Can be changed via web UI

Changes detected within 5 minutes and synced automatically.
```

## Consequences

### Good
* **Clear authority model** - Users know what they can customize
* **Best of both worlds** - Automation where it matters, flexibility where users want it
* **Predictable behavior** - Users understand what will happen
* **Self-healing** - Common operations (credential rotation) don't break integrations
* **Operational clarity** - Juju topology matches infrastructure reality

### Bad
* **More complex reconciliation logic** - Need to check existing state for respectful reconciliation
* **Documentation burden** - Must clearly explain which config is managed vs customizable
* **User learning curve** - Users must understand the category distinctions
* **Potential confusion** - Some users may not read docs and be surprised by aggressive reconciliation

### Mitigations
* Comprehensive README sections explaining management model
* Log warnings when aggressive reconciliation deletes manual config
* Charm status messages when drift is detected and synced
* Consistent patterns across all Charmarr charms

## Related ADRs

- [lib/adr-001-shared-arr-code.md](./adr-001-shared-arr-code.md) - Implements aggressive reconciliation for download clients
- [interfaces/adr-006-media-manager.md](../interfaces/adr-006-media-manager.md) - Implements respectful reconciliation for quality profiles
- [apps/adr-002-cross-app-auth.md](../apps/adr-002-cross-app-auth.md) - Implements self-healing for credentials
