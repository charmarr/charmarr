# Secret Management - Juju Secrets for API Key Distribution

## Context and Problem Statement

Charmarr charms need to exchange API keys and other sensitive credentials to enable cross-application integration. Prowlarr needs API keys to sync indexers to Radarr/Sonarr, media managers need download client credentials, and request managers need media manager API access. The traditional approach of storing credentials directly in Juju relation data bags provides basic access control (only related units can read the data) but lacks features like rotation, audit trails, and defense-in-depth security. The question is: how should charms securely distribute sensitive credentials while supporting operational requirements like key rotation and maintaining appropriate security posture for self-hosted infrastructure?

## Considered Options

* **Option 1: Plaintext in relation data** - Store API keys directly in relation data bags as strings
* **Option 2: Juju Secrets with Kubernetes backend** - Use Juju's secrets system, store actual secrets in Kubernetes Secret objects, share secret IDs via relations
* **Option 3: Juju Secrets with Vault backend** - Use Juju's secrets system with HashiCorp Vault as the storage backend
* **Option 4: External secret management** - Use external tools (Vault, AWS Secrets Manager) independent of Juju

## Decision Outcome

Chosen option: **"Option 2: Juju Secrets with Kubernetes backend for v1"**, because it provides appropriate security for self-hosted infrastructure while enabling future upgrades to Vault without code changes, and is significantly simpler to implement than external secret management while delivering better security than plaintext.

### Architecture Overview

Charms create application secrets and share them through relations by publishing secret IDs rather than actual credentials. The secret lifecycle is bound to the relation lifetime - when a relation is established, secrets are granted to the remote application; when the relation breaks, access is automatically revoked.

**Secret creation and sharing flow:**

1. Provider charm (e.g., Prowlarr) creates or retrieves secret: `self.app.add_secret(content={"api-key": key}, label="prowlarr-api-key")`
2. Provider grants secret to relation: `secret.grant(relation)`
3. Provider publishes secret ID in relation data: `api_key_secret_id: "secret:abc123def456"`
4. Requirer charm (e.g., Radarr) reads secret ID from relation data
5. Requirer retrieves actual secret content: `secret = self.model.get_secret(id=secret_id)`
6. Requirer extracts credentials: `api_key = secret.get_content()["api-key"]`
7. Requirer uses credentials to configure workload

**Secret rotation flow:**

1. Provider generates new API key in workload
2. Provider updates secret: `secret.set_content({"api-key": new_key})`
3. Juju automatically fires `secret-changed` event on all observer units
4. Observers handle event, retrieve new secret: `event.secret.get_content(refresh=True)`
5. Observers reconfigure workloads with new credentials

### V1 Implementation: Kubernetes Backend

For Charmarr v1 on MicroK8s and Canonical Kubernetes, secrets use the **kubernetes backend**:

**Storage mechanism**: Juju stores secret content in Kubernetes Secret objects in the controller namespace. Secret IDs reference these K8s secrets, and Juju handles access control through RBAC.

**Availability**: The kubernetes backend is automatically available when Juju is deployed on a Kubernetes substrate. No additional configuration or infrastructure is required.

**Security properties**:
- Secrets stored in etcd (encrypted at rest if K8s encryption is enabled)
- Access controlled by Kubernetes RBAC
- Secret content never appears in relation data or Juju controller database
- Automatic cleanup when relations break

**Operational simplicity**: Charms use the same `add_secret()`, `grant()`, and `get_secret()` APIs regardless of backend. The backend choice is transparent to charm code.

### V2 Consideration: Vault Backend

Future Charmarr versions may optionally support the **vault backend** for enhanced security:

**Additional capabilities**:
- Hardware Security Module (HSM) integration for key storage
- Detailed audit logs of all secret access
- Compliance certifications (SOC 2, HIPAA, etc.)
- Advanced rotation policies and lease management
- Centralized secret management across multiple Juju models

**Migration path**: Upgrading from kubernetes to vault backend requires no charm code changes. Juju admins configure Vault as a secret backend at the controller level: `juju add-secret-backend myvault vault --config vault.yaml`, then set models to use it: `juju model-config secret-backend=myvault`. Existing secrets automatically migrate.

**Deployment overhead**: Vault requires additional infrastructure (Vault cluster, database backend for Vault storage, HSM for production). This is appropriate for enterprise/production but overkill for personal homelabs.

### Data Model Pattern

Interface data models store secret IDs, not secrets:

```python
class MediaIndexerProviderData(BaseModel):
    api_url: HttpUrl
    api_key_secret_id: str  # "secret:abc123def456"
    base_path: Optional[str] = None

class MediaIndexerRequirerData(BaseModel):
    api_url: HttpUrl
    api_key_secret_id: str  # "secret:xyz789ghi012"
    app_type: ArrAppType
    media_type: MediaType
    instance_name: str
    base_path: Optional[str] = None
```

The `api_key_secret_id` field contains a Juju secret ID (format: `secret:<uuid>`), not the actual API key. This pattern applies to all interfaces that exchange credentials.

### Charm Implementation Pattern

**Provider side (creates and shares secret):**

```python
def _reconcile(self, event):
    api_key = self._get_prowlarr_api_key()

    # Create or update secret
    try:
        secret = self.model.get_secret(label="prowlarr-api-key")
        secret.set_content({"api-key": api_key})
    except SecretNotFoundError:
        secret = self.app.add_secret(
            content={"api-key": api_key},
            label="prowlarr-api-key",
            description="Prowlarr API key for indexer sync"
        )

    # Grant and publish to relation
    for relation in self.indexer_provider.relations:
        secret.grant(relation)
        self.indexer_provider.publish_data(
            relation=relation,
            api_key_secret_id=secret.id  # Just the ID!
        )
```

**Requirer side (consumes secret):**

```python
def _reconcile(self, event):
    provider_data = self.indexer_requirer.get_provider_data(relation)
    if not provider_data:
        return

    # Retrieve actual secret using ID
    prowlarr_secret = self.model.get_secret(id=provider_data.api_key_secret_id)
    prowlarr_api_key = prowlarr_secret.get_content()["api-key"]

    # Use the actual key to configure workload
    self._configure_prowlarr_indexer(prowlarr_api_key)

def _on_secret_changed(self, event):
    # Handle rotation
    new_content = event.secret.get_content(refresh=True)
    new_api_key = new_content["api-key"]
    self._update_prowlarr_credentials(new_api_key)
```

### Rejected Alternatives

**Why not plaintext in relation data:** While relation data bags are only accessible to units involved in the relation, they lack rotation support, audit trails, and defense-in-depth. API keys would appear in Juju controller database dumps and debug logs. Modern secret management requires rotation capabilities for compliance and security best practices. The implementation complexity of Juju Secrets is minimal compared to the security benefits.

**Why not Vault backend for v1:** Vault provides enterprise-grade features but requires significant infrastructure (Vault cluster with HA, database backend, proper HSM configuration). For v1 targeting personal homelabs and small deployments, this is excessive. The kubernetes backend provides appropriate security for the threat model while maintaining operational simplicity. Vault remains available for v2+ when users need enterprise features.

**Why not external secret management:** Using Vault, AWS Secrets Manager, or similar tools outside of Juju would require charms to implement provider-specific APIs, handle authentication to the external system, and manage secret lifecycle independently. This couples charms to specific secret backends and prevents users from choosing their preferred solution. Juju Secrets abstracts the backend choice, allowing the same charm code to work with kubernetes, vault, or future backends.

**Why not user secrets:** Juju supports user-created secrets that admins can grant to applications, but this requires manual secret creation and distribution for every API key. Charm secrets are programmatically managed and automatically tied to relation lifecycle, which matches the dynamic nature of Charmarr deployments where users may add/remove media managers or download clients frequently.

### Security Properties

**Least privilege access**: Secrets are granted only to specific relations. A unit can only access secrets it has been explicitly granted access to. When a relation breaks, access is automatically revoked.

**Rotation support**: The secret-changed event mechanism enables zero-downtime credential rotation. Providers can rotate API keys at any time, and consumers are automatically notified to update their configuration.

**Lifecycle binding**: Secrets are scoped to relation lifetime. When a relation is removed, Juju automatically revokes the secret grant. This prevents orphaned credentials from remaining accessible after components are removed.

### Operational Considerations

**Debugging**: Secret content is not visible in `juju show-unit` or relation data dumps. Operators must use `juju secrets` commands to inspect secret metadata, and only units with granted access can retrieve content via the Juju API.

**Backup and restore**: Secrets are backed up as part of Juju controller backup. When restoring, secret grants are re-established based on relation topology. With kubernetes backend, secrets are in K8s etcd (covered by etcd backup). With vault backend, Vault's own backup mechanisms apply.

**Performance**: Secret retrieval involves Juju API calls and backend queries. For frequently-accessed secrets, charms should cache retrieved values rather than calling `get_secret()` on every reconciliation. The secret-changed event notifies when cached values need refreshing.

### Consequences

* Good, because API keys never appear in relation data, preventing exposure in debug logs and database dumps
* Good, because rotation is natively supported through secret-changed events
* Good, because secret lifecycle is automatically bound to relation lifetime
* Good, because backend choice (kubernetes vs vault) is transparent to charm code
* Good, because v1 requires zero additional infrastructure beyond Kubernetes
* Good, because migration to Vault backend (v2+) requires no code changes
* Good, because the pattern applies uniformly across all Charmarr interfaces
* Bad, because secret retrieval adds API calls compared to reading relation data directly
* Bad, because debugging requires understanding Juju secret commands rather than just inspecting relation data
* Bad, because operators cannot see secret values in standard Juju status output (though this is intentional for security)
* Neutral, because charms must handle secret-changed events, adding event handlers, but this enables rotation which is valuable for security
