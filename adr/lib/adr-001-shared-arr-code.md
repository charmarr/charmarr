# Shared Arr Infrastructure in charmarr-lib

## Context and Problem Statement

Charmarr's arr charms (Radarr, Sonarr, Lidarr, Prowlarr) need to configure their workloads via API calls after receiving relation data. These applications share similar APIs but with key differences:
- **Radarr/Sonarr/Lidarr**: `/api/v3/*` endpoints for download clients, root folders, quality profiles
- **Prowlarr**: `/api/v1/*` endpoints for applications, indexers, host config

Without shared infrastructure, we'd duplicate significant code across 4+ charms for HTTP handling, config transformation, and reconciliation logic.

**Key questions:**
- How should we structure shared code for arr API interactions?
- How should we handle different API versions (v1 vs v3)?
- How should relation data be transformed into workload API payloads?
- What reconciliation semantics should we use (additive vs declarative)?
- How do we handle manually-configured items that weren't created via Juju relations?

## Considered Options

### API Client Architecture
* **Option 1:** Single monolithic `ArrApiClient` with all methods for all apps
* **Option 2:** Inheritance: `ArrApiClient` extends `BaseArrApiClient`, `ProwlarrApiClient` extends `BaseArrApiClient`
* **Option 3:** Separate clients with no code sharing

### Library Structure
* **Option 1:** Single monolithic module
* **Option 2:** Separate concerns: API clients + reconcilers + config builders
* **Option 3:** No shared code - each charm implements its own

### Reconciliation Semantics
* **Option 1:** Additive only - add/update items from relations, never delete
* **Option 2:** Aggressive declarative - delete anything not in relations
* **Option 3:** Managed vs unmanaged - track what we created, only delete those

### Config Building Location
* **Option 1:** Inside API client methods
* **Option 2:** Separate config builder classes
* **Option 3:** Inside reconciler functions

## Decision Outcome

### Shared Enums

All enum definitions are consolidated here to ensure consistency across interfaces:

```python
from enum import Enum

# ========================================
# Shared Enums (used across all interfaces)
# ========================================

class MediaIndexer(str, Enum):
    """Media indexer applications."""
    PROWLARR = "prowlarr"
    JACKETT = "jackett"  # Future
    NZBHYDRA2 = "nzbhydra2"  # Future

class MediaManager(str, Enum):
    """Media manager applications."""
    RADARR = "radarr"
    SONARR = "sonarr"
    LIDARR = "lidarr"
    READARR = "readarr"
    WHISPARR = "whisparr"

class DownloadClient(str, Enum):
    """Download client applications."""
    QBITTORRENT = "qbittorrent"
    SABNZBD = "sabnzbd"
    DELUGE = "deluge"
    TRANSMISSION = "transmission"

class DownloadClientType(str, Enum):
    """Download protocol categories."""
    TORRENT = "torrent"
    USENET = "usenet"

class RequestManager(str, Enum):
    """Request management applications."""
    OVERSEERR = "overseerr"
    JELLYSEERR = "jellyseerr"
```

**Rationale**: Consolidating all enum definitions in charmarr-lib ensures:
- Single source of truth for application identifiers
- No duplicate definitions across interface ADRs
- Easy to extend with new applications
- Type safety across all interface data models

**Interface ADRs reference these enums** rather than redefining them. See:
- [interfaces/adr-003-media-indexer.md](../interfaces/adr-003-media-indexer.md)
- [interfaces/adr-004-download-client.md](../interfaces/adr-004-download-client.md)
- [interfaces/adr-006-media-manager.md](../interfaces/adr-006-media-manager.md)

### API Client: Option 2 - Inheritance with shared base

```python
class BaseArrApiClient:
    """Shared HTTP mechanics for all arr applications."""
    
    def __init__(self, base_url: str, api_key: str, api_version: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_version = api_version
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key

    def _url(self, endpoint: str) -> str:
        return f"{self._base_url}/api/{self._api_version}{endpoint}"

    def _get(self, endpoint: str) -> dict | list:
        response = self._session.get(self._url(endpoint))
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, json: dict) -> dict:
        response = self._session.post(self._url(endpoint), json=json)
        response.raise_for_status()
        return response.json()

    def _put(self, endpoint: str, json: dict) -> dict:
        response = self._session.put(self._url(endpoint), json=json)
        response.raise_for_status()
        return response.json()

    def _delete(self, endpoint: str) -> None:
        response = self._session.delete(self._url(endpoint))
        response.raise_for_status()


class ArrApiClient(BaseArrApiClient):
    """API client for Radarr/Sonarr/Lidarr (/api/v3)."""
    
    def __init__(self, base_url: str, api_key: str):
        super().__init__(base_url, api_key, api_version="v3")

    # Download Clients
    def get_download_clients(self) -> list[dict]: ...
    def add_download_client(self, config: dict) -> dict: ...
    def update_download_client(self, client_id: int, config: dict) -> dict: ...
    def delete_download_client(self, client_id: int) -> None: ...

    # Root Folders
    def get_root_folders(self) -> list[dict]: ...
    def add_root_folder(self, path: str) -> dict: ...

    # Host Config
    def get_host_config(self) -> dict: ...
    def update_host_config(self, config: dict) -> dict: ...

    # Quality Profiles (read-only for media-manager relation)
    def get_quality_profiles(self) -> list[dict]: ...


class ProwlarrApiClient(BaseArrApiClient):
    """API client for Prowlarr (/api/v1)."""
    
    def __init__(self, base_url: str, api_key: str):
        super().__init__(base_url, api_key, api_version="v1")

    # Applications
    def get_applications(self) -> list[dict]:
        return self._get("/application")

    def add_application(self, config: dict) -> dict:
        return self._post("/application", config)

    def update_application(self, app_id: int, config: dict) -> dict:
        return self._put(f"/application/{app_id}", config)

    def delete_application(self, app_id: int) -> None:
        self._delete(f"/application/{app_id}")

    # Host Config
    def get_host_config(self) -> dict:
        return self._get("/config/host")

    def update_host_config(self, config: dict) -> dict:
        return self._put("/config/host", config)

    # Indexers (read-only, user manages via UI)
    def get_indexers(self) -> list[dict]:
        return self._get("/indexer")
```

**Rationale:** 
- `BaseArrApiClient` handles HTTP mechanics shared by all arr apps
- `ArrApiClient` for Radarr/Sonarr/Lidarr with v3 API
- `ProwlarrApiClient` for Prowlarr with v1 API
- Clean separation, no methods that don't belong on each client

### Library Structure: Option 2 - Separate concerns

```
charmarr-lib/
├── interfaces/
│   ├── media_indexer.py        # Relation interface classes + data models
│   ├── download_client.py      # + MEDIA_TYPE_DOWNLOAD_PATHS constant
│   ├── media_manager.py
│   ├── media_storage.py
│   └── vpn_gateway.py
├── arr/
│   ├── base_client.py          # BaseArrApiClient
│   ├── api_client.py           # ArrApiClient (Radarr/Sonarr/Lidarr)
│   ├── prowlarr_client.py      # ProwlarrApiClient
│   ├── reconcilers.py          # Shared reconciler functions
│   └── config_builders.py      # Transform relation data → API payloads
└── reconciler.py               # observe_events utilities
```

### Reconciliation: Option 2 - Aggressive declarative

### Config Building: Option 2 - Separate config builder classes

**Rationale for all:** See detailed explanations below.

## Shared Constants

### MEDIA_TYPE_DOWNLOAD_PATHS

This constant maps media manager types to their download folder names. Used by:
- **Download client charms** (qBittorrent, SABnzbd) - to create categories with correct save paths
- **Arr charms** - to know where downloads will land (for import path configuration)

```python
# In charmarr_lib/interfaces/download_client.py

from enum import Enum

class MediaManager(str, Enum):
    """Media manager applications."""
    RADARR = "radarr"
    SONARR = "sonarr"
    LIDARR = "lidarr"
    READARR = "readarr"
    WHISPARR = "whisparr"

MEDIA_TYPE_DOWNLOAD_PATHS: dict[MediaManager, str] = {
    MediaManager.RADARR: "movies",
    MediaManager.SONARR: "tv",
    MediaManager.LIDARR: "music",
    MediaManager.READARR: "books",
    MediaManager.WHISPARR: "xxx",
}
```

### MEDIA_MANAGER_IMPLEMENTATIONS

Maps media managers to their Prowlarr application implementation details:

```python
# In charmarr_lib/arr/config_builders.py

MEDIA_MANAGER_IMPLEMENTATIONS: dict[MediaManager, tuple[str, str]] = {
    MediaManager.RADARR: ("Radarr", "RadarrSettings"),
    MediaManager.SONARR: ("Sonarr", "SonarrSettings"),
    MediaManager.LIDARR: ("Lidarr", "LidarrSettings"),
    MediaManager.READARR: ("Readarr", "ReadarrSettings"),
    MediaManager.WHISPARR: ("Whisparr", "WhisparrSettings"),
}
```

## Config Builders

### DownloadClientConfigBuilder (for Radarr/Sonarr)

Transform download client relation data into arr API payloads:

```python
class DownloadClientConfigBuilder:
    """Build download client API payloads from relation data."""

    @staticmethod
    def from_provider_data(
        provider: DownloadClientProviderData,
        category: str,
        model: Model,
    ) -> dict:
        """Transform relation data into *arr API payload."""
        if provider.client == DownloadClient.QBITTORRENT:
            return DownloadClientConfigBuilder._build_qbittorrent(provider, category, model)
        elif provider.client == DownloadClient.SABNZBD:
            return DownloadClientConfigBuilder._build_sabnzbd(provider, category, model)
        else:
            raise ValueError(f"Unsupported client: {provider.client}")

    @staticmethod
    def _build_qbittorrent(
        provider: DownloadClientProviderData,
        category: str,
        model: Model,
    ) -> dict:
        # Retrieve secrets (single secret contains both username and password)
        credentials = model.get_secret(id=provider.credentials_secret_id).get_content()
        username = credentials["username"]
        password = credentials["password"]

        # Parse URL
        parsed = urlparse(str(provider.api_url))

        return {
            "enable": True,
            "protocol": "torrent",
            "priority": 1,
            "name": provider.instance_name,
            "implementation": "QBittorrent",
            "configContract": "QBittorrentSettings",
            "fields": [
                {"name": "host", "value": parsed.hostname},
                {"name": "port", "value": parsed.port or 8080},
                {"name": "useSsl", "value": parsed.scheme == "https"},
                {"name": "urlBase", "value": provider.base_path or ""},
                {"name": "username", "value": username},
                {"name": "password", "value": password},
                {"name": "movieCategory", "value": category},  # or tvCategory for Sonarr
            ],
            "tags": [],
        }

    @staticmethod
    def _build_sabnzbd(
        provider: DownloadClientProviderData,
        category: str,
        model: Model,
    ) -> dict:
        api_key = model.get_secret(id=provider.api_key_secret_id).get_content()["api-key"]
        parsed = urlparse(str(provider.api_url))

        return {
            "enable": True,
            "protocol": "usenet",
            "priority": 1,
            "name": provider.instance_name,
            "implementation": "Sabnzbd",
            "configContract": "SabnzbdSettings",
            "fields": [
                {"name": "host", "value": parsed.hostname},
                {"name": "port", "value": parsed.port or 8080},
                {"name": "useSsl", "value": parsed.scheme == "https"},
                {"name": "urlBase", "value": provider.base_path or ""},
                {"name": "apiKey", "value": api_key},
                {"name": "movieCategory", "value": category},
            ],
            "tags": [],
        }
```

### ApplicationConfigBuilder (for Prowlarr)

Transform media-indexer relation data into Prowlarr application payloads:

```python
class ApplicationConfigBuilder:
    """Build Prowlarr application API payloads from relation data."""

    @staticmethod
    def from_requirer_data(
        requirer: MediaIndexerRequirerData,
        prowlarr_url: str,
        model: Model,
    ) -> dict:
        """Transform relation data into Prowlarr application payload."""
        implementation, config_contract = MEDIA_MANAGER_IMPLEMENTATIONS[requirer.manager]

        # Retrieve API key from Juju secret
        secret = model.get_secret(id=requirer.api_key_secret_id)
        api_key = secret.get_content()["api-key"]

        # Parse base URL
        base_url = str(requirer.api_url)
        if requirer.base_path:
            base_url = base_url.rstrip("/") + requirer.base_path

        return {
            "name": requirer.instance_name,
            "syncLevel": "fullSync",
            "implementation": implementation,
            "configContract": config_contract,
            "fields": [
                {"name": "prowlarrUrl", "value": prowlarr_url},
                {"name": "baseUrl", "value": base_url},
                {"name": "apiKey", "value": api_key},
                {"name": "syncCategories", "value": []},
            ],
            "tags": [],
        }
```

## Shared Reconcilers

Declarative, idempotent operations. Each reconciler follows the pattern:
1. Get current state from API
2. Compare against desired state
3. Delete removed, update changed, add new

### reconcile_download_clients (for Radarr/Sonarr)

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
    current = api_client.get_download_clients()
    current_by_name = {dc["name"]: dc for dc in current}

    desired_configs = {}
    for provider in desired_clients:
        config = DownloadClientConfigBuilder.from_provider_data(
            provider=provider,
            category=category,
            model=model,
        )
        desired_configs[provider.instance_name] = config

    # Delete removed (AGGRESSIVE)
    for name, current_dc in current_by_name.items():
        if name not in desired_configs:
            logger.info(f"Removing download client: {name}")
            api_client.delete_download_client(current_dc["id"])

    # Add or update
    for name, desired_config in desired_configs.items():
        existing = current_by_name.get(name)
        if existing:
            if _needs_update(existing, desired_config):
                logger.info(f"Updating download client: {name}")
                api_client.update_download_client(existing["id"], desired_config)
        else:
            logger.info(f"Adding download client: {name}")
            api_client.add_download_client(desired_config)
```

### reconcile_applications (for Prowlarr)

```python
def reconcile_applications(
    api_client: ProwlarrApiClient,
    desired_apps: list[MediaIndexerRequirerData],
    prowlarr_url: str,
    model: Model,
) -> None:
    """Reconcile Prowlarr applications to match desired state from relations.

    IMPORTANT: This is aggressive reconciliation. Any application
    not in desired_apps will be DELETED, including manually-configured
    applications added via the web UI.
    """
    current = api_client.get_applications()
    current_by_name = {app["name"]: app for app in current}

    desired_configs = {}
    for requirer in desired_apps:
        config = ApplicationConfigBuilder.from_requirer_data(
            requirer=requirer,
            prowlarr_url=prowlarr_url,
            model=model,
        )
        desired_configs[requirer.instance_name] = config

    # Delete removed (AGGRESSIVE)
    for name, current_app in current_by_name.items():
        if name not in desired_configs:
            logger.info(f"Removing application: {name}")
            api_client.delete_application(current_app["id"])

    # Add or update
    for name, app_config in desired_configs.items():
        existing = current_by_name.get(name)
        if existing:
            if _needs_update(existing, app_config):
                logger.info(f"Updating application: {name}")
                api_client.update_application(existing["id"], app_config)
        else:
            logger.info(f"Adding application: {name}")
            api_client.add_application(app_config)
```

### reconcile_root_folder

```python
def reconcile_root_folder(
    api_client: ArrApiClient,
    path: str,
) -> None:
    """Ensure root folder exists. Idempotent, additive-only."""
    existing = api_client.get_root_folders()
    if not any(rf["path"] == path for rf in existing):
        logger.info(f"Adding root folder: {path}")
        api_client.add_root_folder(path)
```

### reconcile_external_url

```python
def reconcile_external_url(
    api_client: BaseArrApiClient,  # Works for both ArrApiClient and ProwlarrApiClient
    external_url: str,
) -> None:
    """Configure external URL in host config. Idempotent."""
    current = api_client.get_host_config()
    # ... update if different
```

## Why Aggressive Reconciliation?

We considered only deleting items that Charmarr created while leaving user-managed items alone. **This is fundamentally broken without state:**

1. Deploy qbittorrent-k8s → relate to radarr → "qbittorrent" DC created
2. User manually adds "my-seedbox" via web UI
3. Later: `juju remove-application qbittorrent-k8s`
4. Next reconcile sees two DCs, neither in relation data
5. **Impossible to distinguish** orphaned Charmarr DC from user-managed DC

Without tracking "things I've ever created" (which requires persistent state), we can't implement this safely. The aggressive approach is the only clean stateless option.

**User expectation:** All workload configuration is managed via Juju relations. Manual additions will be removed on next reconciliation.

## Charm Usage

### Radarr Charm

```python
from charmarr_lib.arr.api_client import ArrApiClient
from charmarr_lib.arr.reconcilers import (
    reconcile_download_clients,
    reconcile_root_folder,
    reconcile_external_url,
)

class RadarrCharm(CharmBase):
    def _reconcile(self, event):
        # ...
        self._api_client = ArrApiClient(
            base_url=f"http://localhost:{self._port}",
            api_key=self._get_api_key(),
        )

        reconcile_root_folder(self._api_client, "/data/media/movies")
        reconcile_download_clients(
            api_client=self._api_client,
            desired_clients=self.download_clients.get_providers(),
            category=self.app.name,
            model=self.model,
        )
```

### Prowlarr Charm

```python
from charmarr_lib.arr.prowlarr_client import ProwlarrApiClient
from charmarr_lib.arr.reconcilers import reconcile_applications, reconcile_external_url

class ProwlarrCharm(CharmBase):
    def _reconcile(self, event):
        # ...
        self._api_client = ProwlarrApiClient(
            base_url=f"http://localhost:{self._port}",
            api_key=self._get_api_key(),
        )

        reconcile_applications(
            api_client=self._api_client,
            desired_apps=self.indexer_provider.get_requirers(),
            prowlarr_url=self._get_prowlarr_url(),
            model=self.model,
        )
```

## Consequences

### Good

* **Clean separation**: Base client handles HTTP, subclasses handle app-specific endpoints
* **No method pollution**: `ArrApiClient` doesn't have Prowlarr methods and vice versa
* **Stateless reconciliation**: Relations are single source of truth
* **Idempotent**: Safe to call reconcilers repeatedly
* **Reusable**: API clients work for any arr app, even outside Charmarr
* **DRY**: Hundreds of lines shared across Radarr/Sonarr/Lidarr/Prowlarr

### Bad

* **Aggressive deletion**: Users lose manually-configured items on reconcile
* **No escape hatch**: Can't mix Charmarr-managed + manual configs
* **Library coupling**: Charms depend on charmarr-lib for core functionality
* **API format dependency**: Config builders must track arr API changes

## Documentation Requirements

> **⚠️ Important: Managed Configuration**
>
> Charmarr manages all download client, indexer, application, and related configuration via Juju relations.
>
> **Any manually-added configuration (via web UI) will be removed** on the next reconciliation cycle.
>
> If you need additional download clients, deploy them as Juju charms and create relations.

## Related MADRs

- [apps/adr-004-radarr-sonarr](../apps/adr-004-radarr-sonarr.md) - Media manager charm implementation
- [apps/adr-008-prowlarr](../apps/adr-008-prowlarr.md) - Prowlarr charm implementation
- [apps/adr-007-qbit-sabnzbd](../apps/adr-007-qbit-sabnzbd.md) - Download client charm implementation
- [interfaces/adr-004-download-client](../interfaces/adr-004-download-client.md) - Download client interface
- [interfaces/adr-003-media-indexer](../interfaces/adr-003-media-indexer.md) - Media indexer interface
