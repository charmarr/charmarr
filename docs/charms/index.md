# Charms

!!! note
    This part of the documentation is just for the curious who want to know what Charmarr does behind the scenes. This is not required to deploy or use Charmarr. Feel free to skip it.

Charmarr is composed of multiple charms that thinly wrap the operational layer of the underlying media applications. Each charm runs as a dedicated container alongside the application container in the same pod. This is what allows Charmarr to plug required components together, configure them properly, and keep them running smoothly.

<div class="grid cards" markdown>

-   **Media Server**

    ---

    Plex charm internals.

    [:octicons-arrow-right-24: Read more](media-server.md)

-   **Media Requester**

    ---

    Overseerr charm internals.

    [:octicons-arrow-right-24: Read more](media-requester.md)

-   **Media Manager**

    ---

    Radarr & Sonarr charm internals.

    [:octicons-arrow-right-24: Read more](media-manager.md)

-   **Media Indexer**

    ---

    Prowlarr & Flaresolverr charm internals.

    [:octicons-arrow-right-24: Read more](media-indexer.md)

-   **Download Client**

    ---

    qBittorrent & SABnzbd charm internals.

    [:octicons-arrow-right-24: Read more](download-client.md)

-   **VPN Gateway**

    ---

    Gluetun charm internals.

    [:octicons-arrow-right-24: Read more](vpn-gateway.md)

-   **Storage**

    ---

    Storage charm internals.

    [:octicons-arrow-right-24: Read more](storage.md)

</div>
