# Media Manager Interface Design with Quality Profile Integration

## Context and Problem Statement

Request management tools like Overseerr need to connect to media managers (Radarr, Sonarr) to handle user requests and automatically add content. The media-manager interface enables this integration by publishing connection details and available quality profiles.

**Key challenges:**
- How should quality profiles be passed from Radarr to Overseerr?
- How should default servers be set when multiple Radarr instances exist (e.g., radarr-1080p, radarr-1080p-remux, radarr-4k)?
- How can we respect user customizations made via Overseerr UI while still providing batteries-included defaults?

**Note:** For how quality profiles are created, see [Apps ADR 003](../apps/adr-003-recyclarr-integration.md).

## Considered Options

### Quality Profile Passing
* **Option A:** Pass profiles via relation data - Radarr publishes profiles, Overseerr receives them without API calls
* **Option B:** Overseerr queries Radarr API - Minimal relation data, Overseerr fetches profiles after connection

### Default Server Selection
* **Option 1:** Query Overseerr API before configuration - Check existing defaults, only set if none exists
* **Option 2:** Peer relation state tracking - Store default assignments in Juju peer relation
* **Option 3:** Alphabetical sorting - Deterministic but arbitrary

### Default Profile Selection  
* **Option 1:** Query-first, set-if-empty - Check if profile already set, use existing or pick first
* **Option 2:** Always use first profile - Overwrite any existing configuration
* **Option 3:** User-specified config - Add charm config for profile selection

## Decision Outcome

**Quality profiles:** Option A - Pass via relation data  
**Default server:** Option 1 - Query Overseerr API  
**Default profile:** Option 1 - Query-first, set-if-empty

### Rationale

**Quality profiles in relation data** because:
- Relation data is the contract - Overseerr shouldn't need extra API calls
- When Recyclarr updates profiles, relation-changed event triggers automatic sync
- All necessary data available immediately for Overseerr configuration

**Query Overseerr API for defaults** because:
- Simplest implementation (~30 lines vs ~50 for peer relations)
- Overseerr's database is source of truth - no hidden state in Juju
- Fully idempotent - repeated reconciles don't change user settings
- No peer relation needed

**Query-first for profiles** because:
- Batteries included with sensible defaults (first profile)
- Respects user customization via Overseerr UI
- Simple logic - no profile name parsing needed

### Consequences

* Good: Complete automation - profiles auto-sync from Recyclarr to Overseerr
* Good: User can customize defaults via familiar Overseerr UI without charm interference
* Good: Idempotent reconciliation - safe to run repeatedly
* Good: First-related instance becomes default automatically (predictable)
* Bad: Requires API calls on every reconcile (negligible overhead)
* Bad: First profile is arbitrary (but predictable and can be changed in UI)

## Interface Data Models

### Enums

```python
from charmarr_lib.models import MediaManager, RequestManager

# Note: MediaManager and RequestManager enums are defined in charmarr-lib
# See lib/adr-001-shared-arr-code.md for the consolidated enum definitions
```

### Provider Data Model (Updated with Quality Profiles)

```python
from pydantic import BaseModel, Field
from typing import Optional

class QualityProfile(BaseModel):
    """Quality profile from Radarr/Sonarr"""
    id: int
    name: str  # e.g., "HD-Bluray+WEB", "UHD-Bluray+WEB"

class MediaManagerProviderData(BaseModel):
    """Data published by media manager charms (Radarr, Sonarr, etc.)"""

    # Connection details
    api_url: str = Field(description="Full API URL (e.g., http://radarr:7878)")
    api_key_secret_id: str = Field(description="Juju secret ID containing API key")

    # Identity
    manager: MediaManager = Field(description="Type of media manager")
    instance_name: str = Field(description="Juju app name (e.g., radarr-4k)")
    base_path: Optional[str] = Field(default=None, description="URL base path if configured")

    # Configuration (populated from Radarr API after Recyclarr sync)
    quality_profiles: list[QualityProfile] = Field(description="Available quality profiles")
    root_folders: list[str] = Field(description="Available root folder paths")
    variant: ContentVariant = Field(
        default=ContentVariant.STANDARD,
        description="Content variant: standard (catch-all), uhd (4K), or anime"
    )
```

### Requirer Data Model (Unchanged)

```python
class MediaManagerRequirerData(BaseModel):
    """Data published by request manager charms (Overseerr, Jellyseerr)"""
    
    requester: RequestManager = Field(description="Type of request manager")
    instance_name: str = Field(description="Juju app name")
```

## Implementation Details

### Radarr Charm: Query and Publish Quality Profiles

```python
class RadarrCharm(CharmBase):
    def _reconcile(self, event):
        """Main reconciler - handles all events."""
        # ... other reconciliation logic ...
        
        # After profiles are created (see Apps ADR 003),
        # query and publish them to the media-manager relation
        self._publish_quality_profiles()
    
    def _publish_quality_profiles(self):
        """Query Radarr API and publish profiles to relation."""
        # Query Radarr for current profiles
        profiles_response = requests.get(
            f"{self.radarr_url}/api/v3/qualityprofile",
            headers={"X-Api-Key": self.api_key}
        )
        profiles = [
            QualityProfile(id=p["id"], name=p["name"])
            for p in profiles_response.json()
        ]
        
        # Query root folders
        folders_response = requests.get(
            f"{self.radarr_url}/api/v3/rootfolder",
            headers={"X-Api-Key": self.api_key}
        )
        root_folders = [f["path"] for f in folders_response.json()]

        # Get variant from charm config
        variant = ContentVariant(self.config.get("variant", "standard"))

        # Publish to relation
        provider_data = MediaManagerProviderData(
            api_url=f"http://{self.app.name}:7878",
            api_key_secret_id=self.api_key_secret_id,
            manager=MediaManager.radarr,
            instance_name=self.app.name,
            quality_profiles=profiles,
            root_folders=root_folders,
            variant=variant,
        )
        self.media_manager_provider.publish_data(provider_data)
```

### Overseerr Charm: Query-First Configuration

```python
class OverseerrCharm(CharmBase):
    def _configure_radarr_server(self, provider: MediaManagerProviderData):
        """Configure or update Radarr server in Overseerr."""
        
        # 1. Query existing Radarr servers from Overseerr
        response = requests.get(
            f"{self.overseerr_url}/api/v1/settings/radarr",
            headers={"X-Api-Key": self.overseerr_api_key}
        )
        existing_servers = response.json()
        
        # 2. Check if this server already exists
        existing_server = next(
            (s for s in existing_servers if s['name'] == provider.instance_name),
            None
        )
        
        # 3. Determine default server flag (only if no default exists for this tier)
        # 4K tier: variant == ContentVariant.UHD
        is_4k_tier = provider.variant == ContentVariant.UHD
        has_default_for_tier = any(
            s.get('isDefault', False) and
            s.get('is4k', False) == is_4k_tier
            for s in existing_servers
            if s['name'] != provider.instance_name  # Exclude current server
        )
        is_default = not has_default_for_tier
        
        # 4. Determine quality profile (use existing or pick first)
        if existing_server and existing_server.get('activeProfileId'):
            # User has set a profile - respect it
            profile_id = existing_server['activeProfileId']
        else:
            # No profile set - use first available from Radarr
            profile_id = provider.quality_profiles[0].id
        
        # 5. Configure server in Overseerr
        server_config = {
            "name": provider.instance_name,
            "hostname": provider.api_url.split("://")[1].split(":")[0],
            "port": int(provider.api_url.split(":")[-1]),
            "apiKey": self._get_api_key(provider.api_key_secret_id),
            "useSsl": provider.api_url.startswith("https"),
            "is4k": is_4k_tier,  # UHD variant maps to Overseerr's 4K tier
            "isDefault": is_default,
            "activeProfileId": profile_id,
            "activeDirectory": provider.root_folders[0],
        }
        
        if existing_server:
            # Update existing
            requests.put(
                f"{self.overseerr_url}/api/v1/settings/radarr/{existing_server['id']}",
                headers={"X-Api-Key": self.overseerr_api_key},
                json=server_config
            )
        else:
            # Create new
            requests.post(
                f"{self.overseerr_url}/api/v1/settings/radarr",
                headers={"X-Api-Key": self.overseerr_api_key},
                json=server_config
            )
```

## User Experience Flow

```bash
# Deploy Radarr instances with variant config (see Apps ADR 004):
juju deploy radarr radarr --config variant="standard"
juju deploy radarr radarr-4k --config variant="4k"
juju deploy radarr radarr-anime --config variant="anime"

# Relate to Overseerr:
juju relate overseerr radarr
juju relate overseerr radarr-4k
juju relate overseerr radarr-anime

# Result in Overseerr (automatic):
# - radarr: isDefault=true, is4k=false, profile="HD-Bluray+WEB"
# - radarr-4k: isDefault=true, is4k=true, profile="UHD-Bluray+WEB"
# - radarr-anime: isDefault=false, is4k=false, profile="Anime"

# User can customize in Overseerr UI (optional):
# - Change default server for standard or 4K tier
# - Change default profile per server
# - Charm respects UI changes on next reconcile ✅
```

## Overseerr API Reference

**Get Radarr servers:**
```http
GET /api/v1/settings/radarr
X-Api-Key: {overseerr_api_key}

Response: [
  {
    "id": 1,
    "name": "radarr-1080p",
    "is4k": false,
    "isDefault": true,
    "activeProfileId": 1
  }
]
```

**Add/Update Radarr server:**
```http
POST /api/v1/settings/radarr
PUT /api/v1/settings/radarr/{id}
X-Api-Key: {overseerr_api_key}

Body: {
  "name": "radarr-1080p",
  "hostname": "radarr-1080p",
  "port": 7878,
  "apiKey": "...",
  "is4k": false,
  "isDefault": true,
  "activeProfileId": 1,
  "activeDirectory": "/data/media/movies"
}
```

## Related Decisions

- [Apps ADR 003](../apps/adr-003-recyclarr-integration.md) - How quality profiles are created in Radarr using Trash Guides
- [lib ADR-003](../lib/adr-003-reconciliation-philosophy.md) - Reconciliation philosophy (respectful reconciliation for quality profiles)
- **Media-indexer interface** - Similar passive provider pattern for Prowlarr ↔ arr apps
- **Download-client interface** - Similar passive provider pattern for download clients ↔ arr apps
