# Authentication and Credential Management

Status: Proposed (Some parts need validation)

## Context and Problem Statement

Charmarr integrates multiple media automation applications (Radarr, Sonarr, Prowlarr, SABnzbd, qBittorrent, etc.) that require authentication credentials for both web UI access and programmatic API/HTTP integration. We need to determine:

1. How to handle auto-generated API keys (arr apps, SABnzbd)
2. How to manage qBittorrent HTTP basic auth credentials
3. Whether to manage web UI authentication
4. How to handle credential rotation
5. How to handle credential drift (users changing credentials outside Juju)

The solution must balance automation, security, operational simplicity, and user expectations.

## Decision Drivers

* Complete automation - minimize manual configuration steps
* Security - credentials stored in Juju secrets, not plaintext in config
* User expectations - users expect to use familiar web UIs
* Operational simplicity - self-healing, minimal intervention required
* Juju-native patterns - leverage Juju secrets and relations
* Homelab reality - 5-minute drift windows are acceptable for non-production use

## Considered Options

### For API Key Management (*arr apps, SABnzbd):
* Option A: Read auto-generated keys, store in secrets
* Option B: Attempt to pre-set API keys before startup
* Option C: Force users to manually configure API keys

### For qBittorrent Credentials:
* Option A: Generate credentials, create config before startup
* Option B: Read auto-generated temporary password from logs
* Option C: Require manual credential setup

### For Web UI Authentication:
* Option A: Don't manage - let users configure on first access
* Option B: Provide optional Juju config for automation
* Option C: Force authentication via config editing

### For Credential Rotation:
* Option A: Provide Juju actions, detect drift in update-status
* Option B: Force all rotation via Juju actions, block web UI changes
* Option C: Only support manual web UI rotation

### For Drift Detection:
* Option A: Periodic drift detection in update-status (every 5 min)
* Option B: Real-time file watching (inotify)
* Option C: No drift detection - require manual sync

## Decision Outcome

### API Key Management (*arr apps, SABnzbd)

**Chosen: Option A - Read auto-generated keys**

**Implementation:**
```python
# On pebble-ready or update-status:
1. Read API key from config file (config.xml or sabnzbd.ini)
   OR read from X-Api-Key response header (*arr apps only)
2. Store in Juju secret: {"api-key": "..."}
3. Share secret with requirers via relations
```

**Rationale:**
- API keys are auto-generated on first startup BEFORE web UI authentication is configured
- No official way to pre-set API keys (Sonarr issue #5322 from 2022 still open)
- X-Api-Key header method works without authentication
- Simple, reliable, works with actual application behavior

### qBittorrent Credential Management

**Chosen: Option A - Generate and pre-set credentials**

**Implementation:**
```python
# On install (before first startup):
1. Generate random username + password
2. Create PBKDF2-SHA512 hash (100k iterations, 16-byte salt)
3. Create qBittorrent.conf with credentials
4. Push config to container
5. Start qBittorrent (reads our config)
6. Store plaintext in Juju secret: {"username": "charmarr", "password": "..."}
7. Share with media managers via relation
```

**PBKDF2 Hash Generation:**
```python
import base64, hashlib, os

def generate_qbittorrent_password_hash(password: str) -> str:
    ITERATIONS = 100_000
    SALT_SIZE = 16
    salt = os.urandom(SALT_SIZE)
    hash_bytes = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, ITERATIONS)
    salt_b64 = base64.b64encode(salt).decode()
    hash_b64 = base64.b64encode(hash_bytes).decode()
    return f'@ByteArray({salt_b64}:{hash_b64})'
```

**Rationale:**
- qBittorrent requires HTTP basic auth (username + password)
- Cannot extract plaintext password from config (PBKDF2 hashed)
- Media managers need plaintext password for integration
- We CAN pre-create config with credentials before first startup
- Clean, deterministic, no stop/start dance required
- System user `charmarr` dedicated to automation

**User Considerations:**
- Users can create additional personal accounts via web UI
- Users can change `charmarr` password via web UI (drift detection handles sync)
- Users must NOT delete the `charmarr` user (breaks integration)

### Web UI Authentication

**Chosen: Option A - Don't manage**

**Rationale:**
- Web UI auth is mandatory in Radarr v5+/Sonarr v4+ but set AFTER first access
- Users expect to configure their own web passwords
- Web UI credentials are NOT needed for API/programmatic access
- API keys (arr/SAB) and HTTP basic auth (qBit) are sufficient for automation
- Reduces charm complexity
- Security: users choose their own web passwords

**Documentation Note:**
Users set web UI authentication on first access. This does NOT affect integration - charms only use API keys or HTTP basic auth credentials.

### Credential Rotation

**Chosen: Hybrid approach - support both Juju and web UI rotation**

While we decide to support both methods, we should discourage users from using the web UI for rotation. What Charmarr offers is quite secure, so there should be no need for users to do this manually.

**Implementation:**
```python
# Method 1: Via config file edit + restart (all apps)
1. Generate new credential/key
2. Push updated config file (config.xml, sabnzbd.ini, qBittorrent.conf)
3. container.restart("app-name")
4. Update Juju secret with new value
5. secret-changed event propagates to requirers
6. Requirers update their configs automatically

# Method 2: Via web UI (user action)
# Handled by drift detection (see below)
```

**Rationale:**
- Config file approach is clean and atomic
- Users will naturally use web UI (familiar interface)
- Supporting both provides flexibility
- Drift detection makes web UI rotation safe

### Drift Detection and Reconciliation

**Chosen: Option A - Periodic detection in update-status**

**Implementation:**
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
        # Triggers secret-changed on all observers
        self.unit.status = ActiveStatus("Running (credentials auto-synced)")
```

**Applies to:**
- All *arr apps API keys
- SABnzbd API key
- qBittorrent username + password

**Maximum Drift Window:** 5 minutes (update-status interval)

**Rationale:**
- Users WILL rotate credentials via web UI despite documentation
- Self-healing is better than requiring manual intervention
- 5-minute drift window is acceptable for homelab use cases
- Simple implementation (no file watching complexity)
- Consistent pattern across all apps
- Juju secret-changed events handle propagation automatically

### Consequences

**Good:**
* Complete automation - no manual credential configuration required
* Self-healing - credentials auto-sync when changed via web UI
* Secure - credentials stored in Juju secrets, shared via relations
* User-friendly - users can use familiar web UI for credential changes
* Consistent - same pattern (drift detection + reconciliation) for all apps
* Clean separation - API/integration credentials managed by charms, web UI auth managed by users
* Rotation support - credentials fully rotatable via config updates
* Zero manual configuration - qBittorrent credentials set before first startup

**Bad:**
* Drift window - up to 5 minutes of broken integration after web UI credential changes
* No real-time detection - relies on periodic update-status hook
* Edge case complexity - must handle credential changes during reconciliation
* PBKDF2 complexity - qBittorrent hash generation adds code complexity

**Mitigations:**
* Document drift behavior and expected recovery time. And discourage web UI rotation.
* Log warnings when drift is detected for observability
* Ensure idempotent reconciliation (safe to run multiple times)
* Test credential rotation thoroughly in CI

## Technical Details

### Config File Locations

| App | Config Path | Credential Field |
|-----|-------------|------------------|
| Radarr/Sonarr/Prowlarr/Lidarr | `~/.config/App/config.xml` | `<ApiKey>` |
| SABnzbd | `~/.sabnzbd/sabnzbd.ini` | `api_key = ...` |
| qBittorrent | `~/.config/qBittorrent/qBittorrent.conf` | `WebUI\Username=...`<br>`WebUI\Password_PBKDF2=...` |

### Juju Secret Schemas

```python
# *arr apps and SABnzbd:
{
    "api-key": "32-character-hex-string"
}

# qBittorrent:
{
    "username": "charmarr",
    "password": "random-generated-plaintext"  # For sharing with media managers
}
```

### Credential Sharing via Relations

**media-indexer interface** (Prowlarr → Radarr/Sonarr):
```python
# Provider (Prowlarr) shares:
relation_data["api-key-secret-id"] = secret.id

# Requirer retrieves:
secret = self.model.get_secret(id=secret_id)
api_key = secret.get_content()["api-key"]
```

**download-client interface** (qBit/SAB → Media Managers):
```python
# qBittorrent provider shares (single secret with both fields):
relation_data["credentials_secret_id"] = secret.id

# Radarr requirer retrieves:
secret = self.model.get_secret(id=secret_id)
credentials = secret.get_content()
username = credentials["username"]
password = credentials["password"]

# SABnzbd provider shares:
relation_data["api_key_secret_id"] = secret.id

# Radarr requirer retrieves:
secret = self.model.get_secret(id=secret_id)
api_key = secret.get_content()["api-key"]
```

### Security Properties

* **Least Privilege**: Secrets only shared with specific relations
* **Lifecycle Binding**: Secrets auto-revoked when relation breaks
* **Rotation Support**: Secret content updatable, triggers secret-changed events
* **Backend Agnostic**: K8s secrets in v1, can migrate to Vault without code changes
* **No Plaintext in Config**: qBittorrent uses PBKDF2 hashes in config file
* **Secure Generation**: Cryptographically secure random passwords via `secrets` module

## Documentation Requirements

### User-Facing Documentation

**Automatic Credential Management**

Charmarr automatically manages integration credentials:
- API keys for Radarr, Sonarr, Prowlarr, Lidarr, SABnzbd
- Username and password for qBittorrent

These credentials are:
- Auto-generated on installation
- Stored securely in Juju secrets
- Automatically shared between integrated applications
- Self-healing if changed via web UI

**Credential Rotation via Web UI**

You can rotate credentials through the application web UIs. While this can be done, it is recommended to not do this through the web UI to avoid temporary integration failures. But Charmarr is designed to detect these changes and automatically sync the credentials back to Juju secrets. There may be up to 5 minutes where integrations fail with authentication errors after credential rotation. This is normal and self-healing.

Or something like that.

**Additional qBittorrent Users**

The `charmarr` user is created for automation. You can:
- ✅ Create additional personal users via Settings → Web UI
- ✅ Change the `charmarr` user's password (auto-synced)
- ❌ DO NOT delete the `charmarr` user - it breaks integration

**Web UI Authentication**

On first access to each application's web UI, you'll be prompted to set up authentication (username/password). This is separate from the API credentials Charmarr manages and only affects web UI access.

### Operator Documentation

**Drift Detection Algorithm**

Every 5 minutes (update-status interval):
1. Read current credential from config file
2. Compare with value in Juju secret
3. If different:
   - Log warning
   - Update secret to match config file
   - Trigger secret-changed event on all observers
4. Observers (requirers) update their download client configs

## Implementation Checklist

- [ ] Implement drift detection in update-status for all charms
- [ ] Add PBKDF2 hash generation for qBittorrent charm
- [ ] Update interface libraries with secret ID passing
- [ ] Add secret-changed event handlers in requirer charms
- [ ] Write integration tests for credential rotation
- [ ] Write integration tests for drift detection
- [ ] Document credential management in README
- [ ] Add logging for drift detection events
- [ ] Test credential rotation across the stack

## Related Decisions

* [Interfaces ADR-002](../interfaces/adr-002-secret-management.md): Secret Management (establishes Juju Secrets as the storage mechanism)
* [lib ADR-003](../lib/adr-003-reconciliation-philosophy.md): Reconciliation Philosophy (establishes self-healing pattern for credentials)
