# FAQ

## Setup

??? question "What Kubernetes distros are supported?"
    MicroK8s is recommended and tested. Other Kubernetes distributions with Calico CNI should work. If your cluster uses Cilium, see the [Compatibility Checklist](setup/prerequisites.md#compatibility-checklist) in prerequisites.

??? question "What are the hardware requirements?"
    Charmarr has more overhead than a simple Docker Compose setup. Kubernetes and Juju add resource consumption. As someone smart once said, there's no free lunch. Charmarr's benefits come with a price to pay.

    Minimum: 8 GB RAM, 4 vCPUs. More is better, especially during initial deployment.

??? question "Can I run Charmarr on a Raspberry Pi?"
    Untested. Theoretically possible on a Pi 5 with sufficient RAM, but expect performance constraints. The initial deployment is resource-intensive. If you try it, let me know how it goes.

## Storage

??? question "Why do I need shared storage?"
    Shared storage enables hardlinks between download clients and media managers. When qBittorrent finishes downloading, Radarr/Sonarr can hardlink the file to your media library instead of copying it. This is instant and uses no extra disk space. See [Storage](charms/storage.md) for details.

??? question "What are hardlinks?"
    A hardlink is a filesystem feature where two filenames point to the same data on disk. Unlike copies, hardlinks use no additional space. Charmarr uses hardlinks to move completed downloads to your media library instantly without duplicating files.

??? question "Can I use my existing NFS share?"
    Yes. Configure the storage charm with `backend-type=native-nfs` and point it to your NFS server. See [Storage](setup/quickdeploy.md#storage) for configuration.

    One caveat: don't run the NFS server on the same node as Charmarr. Loopback NFS mounts can cause deadlocks.

## Networking

??? question "Do I need a VPN subscription?"
    Recommended, but not required. Charmarr works best with a WireGuard-compatible VPN for traffic anonymization. ProtonVPN is recommended. See [VPN Provider](setup/quickdeploy.md#vpn-provider) for supported providers.

    To run without a VPN, set `unsafe-mode` to `true` for qBittorrent and SABnzbd. This is intentionally made hard because it's discouraged.

    **Manual Deploy:**

    ```bash
    juju config qbittorrent unsafe-mode=true
    juju config sabnzbd unsafe-mode=true
    ```

    **Quick Deploy:**

    After deployment, remove the VPN relations and configure unsafe mode:

    ```bash
    juju remove-relation gluetun qbittorrent
    juju remove-relation gluetun sabnzbd
    juju remove-relation gluetun prowlarr
    juju config qbittorrent unsafe-mode=true
    juju config sabnzbd unsafe-mode=true
    ```

    **Without a VPN, your real IP is exposed to torrent trackers and usenet providers.**

??? question "Can I use OpenVPN instead of WireGuard?"
    No. Charmarr only supports WireGuard. OpenVPN support is not planned.

??? question "Do I need the service mesh?"
    Probably not. It's enterprise-level network hardening made as simple as it can get for homelab use. Do I need it? Most likely not. But homelab is not a place where one does things one needs, it's a place where one does things one wants and can. Does Charmarr make service mesh accessible to any homelab user? Absolutely.

    Istio is disabled by default. Enable with `enable_istio = true` and `enable_mesh = true` in Quick Deploy after checking the [Compatibility Checklist](setup/prerequisites.md#compatibility-checklist). Charmarr works fine without it at homelab level.

    Why include it? Partly to dogfood my own project from work, but also to expose it to a wider audience who are curious enough to try it. See [Networking](security/network.md) for what it does.

??? question "What happens if my VPN connection drops?"
    A two-way killswitch protects you. If the VPN drops, Gluetun's internal firewall blocks traffic. If the Gluetun pod dies, Kubernetes NetworkPolicies block traffic. Your real IP is never exposed. See [Networking](security/network.md) for details.

## Apps

??? question "How do I access the web UIs?"
    With Istio ingress, each app is accessible via the ingress gateway. The URLs follow this pattern:

    - Radarr: `http://<ARR_INGRESS_IP>:443/radarr`
    - Sonarr: `http://<ARR_INGRESS_IP>:443/sonarr`
    - Prowlarr: `http://<ARR_INGRESS_IP>:443/prowlarr`
    - qBittorrent: `http://<ARR_INGRESS_IP>:443/qbittorrent`
    - Plex: `http://<PLEX_INGRESS_IP>:443`
    - Overseerr: `http://<OVERSEERR_INGRESS_IP>:443`

    See [Post-Deploy](setup/post-deploy.md) for details on finding ingress IPs. If you're not using Istio, find the URLs based on your ingress setup.

??? question "Why port 443 with HTTP?"
    Charmarr plans to integrate with Tailscale to securely expose ingress services on your tailnet for remote access. The Tailscale operator exposes all service ports, so Charmarr uses port 443 to be ready for this integration. The port may become configurable in the future. For now, yes, it's unfortunately HTTP on port 443.

??? question "Can I add more Radarr/Sonarr instances?"
    Yes. Deploy additional instances with unique names and variants. For example:

    ```bash
    juju deploy radarr-k8s --trust radarr-4k
    juju config radarr-4k variant=4k ingress-path=/radarr-4k
    ```

    See [Manual Deploy](setup/manual.md#media-managers) for details.

??? question "What are my qBittorrent credentials?"
    Credentials are auto-created by the charm and stored as Juju secrets. See [qBittorrent](setup/post-deploy.md#qbittorrent-access-optional) for how to retrieve them.

??? question "Can I use apps that Charmarr doesn't support?"
    Charmarr uses Juju relations as the single source of truth for declaratively reconciling the system. If you manually add an app or connection, Charmarr will likely remove it during the next reconciliation cycle. This is a conscious design decision to keep Charmarr robust and predictable.

## Migration

??? question "Can I migrate from Docker Compose?"
    Yes. Charmarr delivers a complex architecture with simplicity. Setup and maintenance should be easier than managing Docker Compose files manually. However, migration paths from existing setups are not yet documented or tested.

??? question "Can I use my existing media library?"
    Theoretically, yes. If your existing media folder follows the [TRaSH Guides](https://trash-guides.info/) folder structure (`/data/media/movies`, `/data/media/tv`, etc.), Charmarr should work with it. The charms add root folders additively and don't delete existing content.

    The recommended approach:

    1. Deploy Charmarr and let it create the folder structure
    2. Copy your existing media into the appropriate folders
    3. Use Radarr/Sonarr's Library Import feature to add existing media

    **This is theoretical and expected behavior but currently untested. Proceed with caution and keep backups.**

## Troubleshooting

??? question "Why is my CPU usage high during initial deployment?"
    Quick Deploy throws many requests at the Juju controller simultaneously. This causes temporary CPU spikes. Once the deployment settles, CPU usage drops significantly. This is normal.

    Manual Deploy should have lower CPU usage since it's a step-by-step process.

??? question "My initial `tofu apply` misbehaved. What do I do?"
    The easiest solution is to destroy and reapply:

    ```bash
    tofu destroy
    tofu apply -auto-approve
    ```

    Charmarr follows a [reconciliation pattern](https://www.chainguard.dev/unchained/the-principle-of-reconciliation), so the order of connections shouldn't matter. However, `tofu apply` throws all connections at the Juju controller at once, which can occasionally cause unexpected states. A fresh apply usually resolves this.

??? question "An app is stuck in an error state. What do I do?"
    First, check the logs:

    ```bash
    kubectl logs -n charmarr deploy/<app-name>
    ```

    If the error makes sense, address it. If not, the quickest fix is to delete the affected pod and let Kubernetes recreate it:

    ```bash
    kubectl delete pod -n charmarr -l app.kubernetes.io/name=<app-name>
    ```

    If the issue persists, [open an issue](https://github.com/charmarr/charmarr/issues) with the logs.

??? question "How do I view logs?"
    Use kubectl:

    ```bash
    # App logs
    kubectl logs -n charmarr deploy/<app-name>

    # Charm logs
    kubectl logs -n charmarr deploy/<app-name> -c charm

    # Follow logs in real-time
    kubectl logs -n charmarr deploy/<app-name> -f
    ```
