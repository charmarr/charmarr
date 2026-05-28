# Recyclarr Integration in Arr Charms for Automated Quality Profile Management

## Context and Problem Statement

Charmarr aims to provide better automation than Docker Compose setups. A key pain point in media management is configuring quality profiles and custom formats in Radarr/Sonarr to automatically select high-quality releases while avoiding low-quality ones. Trash Guides provides community-maintained best practices, and Recyclarr syncs these configurations via API calls.

**Key questions:**
- Should Recyclarr be embedded in arr charms, run as a separate charm, or left to manual user configuration?
- How should quality profiles be configured - via Juju config, web UI, or automation?
- When should Recyclarr sync run - on startup, on schedule, or manually?

## Considered Options

* **Option A:** Embed Recyclarr in arr charms - Bundle binary, run during reconciliation
* **Option B:** Sidecar container - Run Recyclarr as a separate container in the same pod
* **Option C:** Separate Recyclarr charm - Deploy as CronJob, relate to arr apps
* **Option D:** Manual user configuration - Users run Recyclarr themselves or configure profiles manually

## Decision Outcome

Chosen option: **Option B - Sidecar container**, because it provides the same UX benefits as embedding while using standard OCI images and avoiding binary management in the charm.

### Rationale

**Why sidecar container (not embedded binary):**
- Uses official Recyclarr OCI image (`ghcr.io/recyclarr/recyclarr:latest`)
- No need to bundle binaries in charmcraft parts
- Automatic updates via Juju resource management
- Same pod networking allows localhost API access to arr apps

**Why not separate charm:**
- Recyclarr is a simple CLI tool, not a complex service
- Separate charm adds maintenance burden, relation design, duplicate credentials
- No architectural complexity needed

**Why automate (not manual):**
- This is a key differentiator vs Docker Compose (batteries included)
- Quality profiles are complex - Trash Guides community expertise valuable
- Optional feature - users can disable via config for manual control
- Profiles stay internal to each arr instance (no interface pollution)

**When Recyclarr Runs:**

1. **Every reconciliation** if `trash-profiles` config is set (idempotent operation)
   - This includes: install, upgrade, config-changed, relation changes, secret changes
   - Recyclarr is fast (~2-5 sec) and idempotent, so safe to run frequently
   - Ensures profiles stay in sync even if manually deleted via web UI
   - Profile data is published to relations after each sync

2. **Via manual action** (`juju run radarr sync-trash-profiles`)
   - Use when Trash Guides update their recommendations
   - Forces immediate sync without waiting for next reconcile event

3. **NOT on schedule** - No background cron job
   - Reduces unnecessary API calls to Radarr
   - User controls when updates happen via action or by triggering reconcile

**Rationale for "every reconcile"**: Juju spawns fresh Python process per event,
so state tracking ("has run once") is impossible without storing state in Juju
peer relation. Running on every reconcile is simpler than managing persistent state,
and the performance cost is negligible (~2-5 seconds per reconcile).

### Consequences

* Good: Massive UX win - auto-configured Trash Guides profiles
* Good: Uses official OCI image - no binary management
* Good: Optional - disable via config for manual control
* Good: No interface pollution - quality profiles stay internal to arr instance
* Good: Fits "for the love of the game" philosophy
* Good: Recyclarr updates independent of charm updates (via Juju resources)
* Neutral: First profile becomes default in Overseerr (arbitrary but can be changed)

## Implementation Design

### Charm Configuration

```yaml
# Radarr charm config.yaml
trash-profiles:
  type: string
  default: ""
  description: |
    Comma-separated list of Trash Guide profile templates to sync.
    Examples: "hd-bluray-web", "uhd-bluray-web", "remux-web-1080p", "anime"
    
    Leave empty to skip auto-configuration (manual profile management).
    Profiles are synced on startup. Use 'sync-trash-profiles' action to re-sync.
    
    See: https://trash-guides.info/Radarr/
    
    Available templates:
    - hd-bluray-web: 1080p Bluray + WEB-DL
    - uhd-bluray-web: 4K Bluray + WEB-DL  
    - remux-web-1080p: 1080p Remux + WEB-DL
    - remux-web-2160p: 4K Remux + WEB-DL
    - anime: Anime-optimized profiles
```

```yaml
# actions.yaml
sync-trash-profiles:
  description: |
    Manually sync quality profiles and custom formats from Trash Guides.
    Run this when Trash Guides update their recommendations.
```

### Charmcraft Configuration (Sidecar Container)

```yaml
# charmcraft.yaml
containers:
  radarr:
    resource: radarr-image
    mounts:
      - storage: config
        location: /config
  recyclarr:
    resource: recyclarr-image

resources:
  radarr-image:
    type: oci-image
    description: OCI image for Radarr (LinuxServer)
    upstream-source: lscr.io/linuxserver/radarr:latest
  recyclarr-image:
    type: oci-image
    description: OCI image for Recyclarr
    upstream-source: ghcr.io/recyclarr/recyclarr:latest
```

### Charm Implementation

The charm executes Recyclarr in the sidecar container via Pebble:

```python
def _sync_trash_profiles(self, api_key: str) -> None:
    """Sync Trash Guides quality profiles via Recyclarr sidecar container."""
    profiles_config = str(self.config.get("trash-profiles", "")).strip()
    if not profiles_config:
        # Use variant defaults if no explicit config
        profiles_config = get_default_trash_profiles(self._variant)
    if not profiles_config:
        return

    container = self.unit.get_container("recyclarr")
    if not container.can_connect():
        logger.warning("Recyclarr container not ready, skipping profile sync")
        return

    sync_trash_profiles(
        container=container,
        manager=MediaManager.RADARR,
        api_key=api_key,
        profiles=profiles_config,
        api_url="http://localhost:7878",
    )
```

The `sync_trash_profiles` function from charmarr-lib:
1. Generates a Recyclarr YAML config
2. Pushes it to the sidecar container
3. Executes `recyclarr sync` via Pebble exec
4. Parses output for errors

## User Experience

```bash
# Deploy with Trash Guides profiles
juju deploy radarr radarr-1080p --config trash-profiles="hd-bluray-web"
juju deploy radarr radarr-4k --config trash-profiles="uhd-bluray-web"

# Profiles auto-created on startup:
# - radarr-1080p: "HD-Bluray+WEB" profile created
# - radarr-4k: "UHD-Bluray+WEB" profile created

# User can add additional profiles via web UI (charm doesn't interfere)

# Later, Trash Guides update their recommendations:
juju run radarr-1080p sync-trash-profiles

# Profiles updated, relation-changed triggers Overseerr to pick up changes
```

## Quality Profile Validation

**Resolution mixing prevention:**

```python
def _validate_trash_profiles(self, profiles_config: str) -> None:
    """Ensure all profiles are same resolution (prevent mixing 1080p and 4K)."""
    profiles_list = [p.strip() for p in profiles_config.split(",")]
    
    has_1080p = any("1080p" in p or "hd-" in p for p in profiles_list)
    has_4k = any("2160p" in p or "uhd-" in p or "4k" in p for p in profiles_list)
    
    if has_1080p and has_4k:
        raise ValueError(
            "Cannot mix 1080p and 4K profiles in same instance. "
            "Deploy separate instances: radarr-1080p and radarr-4k"
        )
```

## Available Trash Guides Templates

**Radarr:**
- `hd-bluray-web` - 1080p Bluray + WEB-DL (most common)
- `uhd-bluray-web` - 4K Bluray + WEB-DL (4K instance)
- `remux-web-1080p` - 1080p Remux + WEB-DL (high quality)
- `remux-web-2160p` - 4K Remux + WEB-DL (highest quality)
- `anime` - Anime-optimized with group tiers

**Sonarr:**
- `web-1080p` - 1080p WEB-DL
- `web-2160p` - 4K WEB-DL  
- `anime` - Anime-optimized

**Profile naming:**
Templates create profiles with standardized Trash Guides names:
- `hd-bluray-web` → "HD-Bluray+WEB"
- `uhd-bluray-web` → "UHD-Bluray+WEB"
- `remux-web-1080p` → "Remux-1080p"

## Integration with Media-Manager Interface

After Recyclarr creates profiles in Radarr:

```
1. Recyclarr creates profiles in Radarr
   └─> Radarr API: POST /api/v3/qualityprofile

2. Radarr charm queries profiles  
   └─> Radarr API: GET /api/v3/qualityprofile
   
3. Radarr charm publishes to relation
   └─> See [Interfaces ADR 006](../interfaces/adr-006-media-manager.md) for how profiles flow to Overseerr
```

## Key Technical Details

**Why Recyclarr runs as sidecar container:**
- All containers in same Kubernetes pod share networking
- Recyclarr can access `localhost:7878` (Radarr API)
- Uses official OCI image - no binary management
- Cleaner separation: charm orchestrates, containers run services

**Container setup:**
- Recyclarr image: `ghcr.io/recyclarr/recyclarr:latest`
- Managed via Pebble (no persistent service - runs on demand)
- Config generated and pushed to container at runtime

**API access:**
- Recyclarr calls: `http://localhost:7878/api/v3/*`
- Same pod networking enables this
- Uses API key from Juju secret

## Related Decisions

- [Interfaces ADR 006](../interfaces/adr-006-media-manager.md) - How quality profiles flow from Radarr to Overseerr via relation data, including query-first default selection logic
