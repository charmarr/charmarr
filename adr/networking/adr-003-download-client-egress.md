# Download Client VPN Integration Method

**Status:** Accepted

## Context and Problem Statement

Download client pods need to be configured to route their traffic through the VPN gateway via VXLAN. This requires injecting init containers, sidecars, adding NET_ADMIN capability, and configuring routing rules. How do we automate this configuration in a way that aligns with Juju's charm-based orchestration model?

## Considered Options

* **Mutating webhook (admission controller)** - Kubernetes webhook automatically injects containers when pods are created
* **Juju relations + lightkube StatefulSet patching** - Download client charms relate to gluetun, then patch their own StatefulSet
* **VPN charm patches consumers** - gluetun-k8s charm patches consumer StatefulSets
* **Manual pod labels + external controller** - Label pods, separate controller watches and patches

## Decision Outcome

Chosen option: **"Juju relations + lightkube StatefulSet patching"**, because it leverages Juju's existing relation system to communicate configuration, keeps modification logic in the consuming charms (single responsibility), avoids webhook infrastructure complexity (certificates, admission controller deployment), maintains clean resource ownership (each charm manages its own resources), and makes VPN routing topology visible via `juju status --relations`.

### Implementation Approach

Consumer charms use `VPNGatewayRequirer` from vpn-k8s-lib, which provides a `reconcile()` method that handles StatefulSet patching. The library reads `routing_method` from relation data and applies the appropriate patching strategy (currently pod-gateway).

The library uses **strategic merge patch** to add containers without replacing Juju's existing containers. This is the same pattern validated for storage patching.

**Resource ownership principle**: Each charm patches its own resources. The gluetun-k8s charm patches itself with gateway containers; consumer charms patch themselves with client containers. Neither modifies resources it doesn't own.

### What Gets Patched (Consumer Side)

When a download client relates to gluetun-k8s, vpn-k8s-lib patches the consumer's StatefulSet to add:

1. **Init container** (`pod-gateway:client_init.sh`):
   - Creates VXLAN interface pointing to gateway pod
   - Gets IP via DHCP from gateway
   - Modifies routing table (default route via VXLAN, except cluster CIDRs)
   - Requires `NET_ADMIN` capability

2. **Sidecar container** (`pod-gateway:client_sidecar.sh`):
   - Monitors gateway connectivity via periodic pings
   - Detects when gateway pod restarts (gets new K8s IP)
   - Resets VXLAN to discover new gateway IP
   - ~3MB RAM overhead

3. **NetworkPolicy** (kill switch):
   - Blocks all egress except cluster CIDRs
   - If VXLAN routing fails, traffic blocked at K8s level
   - Created as separate resource, owned by consumer charm

### Why Consumer Self-Patching (Not Webhook)

**Mutating webhook would require:**
- Webhook server deployment (another thing to manage)
- TLS certificates (cert-manager dependency or self-signed PKI)
- MutatingWebhookConfiguration (cluster-scoped resource)
- Failure mode complexity (`failurePolicy: Fail` blocks pods, `Ignore` leaks traffic)

**Consumer self-patching provides:**
- Topology visible in `juju status --relations`
- Clear which client uses which gateway
- No certificate management
- Failure mode is clear (charm goes to error status)
- Same pattern as storage patching (already validated)

### Consequences

* Good, because declarative - `juju relate qbittorrent gluetun` makes intent clear
* Good, because topology visible - `juju status --relations` shows VPN routing relationships
* Good, because simpler - no webhook certificates, admission controller, or ValidatingWebhookConfiguration
* Good, because charm-native - uses Juju's relation system rather than fighting it
* Good, because clean ownership - each charm manages its own Kubernetes resources
* Good, because strategic merge patch safely coexists with Juju's container management
* Good, because consumer charms already require `--trust` for storage patching (no new permissions)
* Good, because routing method communicated via relation data (extensible)
* Bad, because requires lightkube dependency in download client charms (via vpn-k8s-lib)
* Bad, because requires RBAC permissions for charms to patch their own StatefulSets
* Bad, because client sidecar adds ~3MB RAM per consumer pod (negligible)

**Why NOT "VPN charm patches consumers":**
- Breaks resource ownership principle
- gluetun-k8s would need cluster-wide RBAC to patch arbitrary StatefulSets
- Ordering dependencies unclear (what if consumer deployed first?)
- Cleanup responsibility fuzzy (who removes containers when relation breaks?)

**Rejected: Mutating webhook:**
- Adds significant infrastructure complexity
- Less visible in Juju topology
- Certificate management burden
- Privacy-critical feature shouldn't depend on webhook availability

## Implementation Requirements (Validated 2025-12-11)

### Client-Side Requirements

**1. ConfigMap with Settings (CRITICAL - Formatting Confusion)**

**CONFUSING BUT CORRECT**: Client ConfigMap uses **space-separated** CIDRs (different from gateway env vars which use commas).

Consumer pods MUST mount a ConfigMap at `/config` with literal values (not shell variable substitution):

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pod-gateway-settings
data:
  settings.sh: |
    K8S_DNS_IPS="10.152.183.10"
    NOT_ROUTED_TO_GATEWAY_CIDRS="10.1.0.0/16 10.152.183.0/24"  # spaces!
```

**Why space-separated?** The pod-gateway client_init.sh script does:
```bash
for local_cidr in $NOT_ROUTED_TO_GATEWAY_CIDRS; do
  ip route add "$local_cidr" via "$K8S_GW_IP"
done
```
Shell word splitting on spaces is intentional. **Commas will not work here.**

**Why K8S_DNS_IPS is required**: The client_init.sh script does `dig +short $GATEWAY_NAME @$K8S_DNS_IP`. Without explicit DNS IP, this fails. After routing manipulation, normal DNS resolution may not work.

**Why NOT_ROUTED_TO_GATEWAY_CIDRS is required**: The script adds explicit routes for these CIDRs via K8s gateway BEFORE deleting the default route. Without this:
- Pod can't reach CoreDNS for gateway hostname resolution
- Pod can't reach the gateway pod itself (pod IP is in pod CIDR)
- Pod can't reach any cluster services
- Init container fails

**Why ConfigMap not env vars?** The pod-gateway scripts source `/config/settings.sh` to read configuration. Environment variables passed directly to the containers don't work - the script specifically looks for the ConfigMap file.

**2. Deployment Ordering (CRITICAL)**

Gateway MUST be fully ready BEFORE client pods deploy:

```bash
# 1. Deploy gateway
kubectl apply -f gateway.yaml

# 2. Wait for ready
kubectl wait --for=condition=ready pod/gluetun-0 -n vpn-test --timeout=120s

# 3. Deploy client
kubectl apply -f client.yaml
```

**Why**: If client deploys while gateway is still starting:
- DNS resolution of gateway hostname fails
- VXLAN connection fails (gateway not listening)
- DHCP lease fails (gateway DHCP server not ready)
- Client init container goes into CrashLoopBackOff

**In charm code**: The consumer charm should check `vpn_connected` field from provider relation data before patching its StatefulSet.

**3. Volume Mount for ConfigMap**

Both init and sidecar containers need the ConfigMap mounted:

```yaml
volumeMounts:
  - name: config
    mountPath: /config
volumes:
  - name: config
    configMap:
      name: pod-gateway-settings
```

The pod-gateway scripts source `/config/settings.sh` to read configuration.

### Validation Results

**Tested on MicroK8s with Calico CNI:**
- ✅ Cross-namespace routing works (gateway in vpn-test, client in vpn-client-test)
- ✅ Cluster DNS resolution preserved (kubernetes.default.svc.cluster.local)
- ✅ Pod-to-pod connectivity preserved (10.1.0.0/16)
- ✅ Service connectivity preserved (10.152.183.0/24)
- ✅ External traffic routes through VPN (verified via public IP check)
- ✅ Auto-recovery after gateway restart (~10 seconds)
- ✅ VXLAN interface gets new DHCP IP on reconnect
