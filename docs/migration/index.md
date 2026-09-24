# Migration

Guides for moving between Charmarr releases and swapping components.

<div class="grid cards" markdown>

-   **Overseerr → Seerr**

    ---

    Upstream Overseerr has merged with Jellyseerr into a new project,
    **Seerr**. The `overseerr-k8s` charm is deprecated and will be
    removed in a future release. Migrate to `seerr-k8s` for ongoing
    support and Jellyfin/Emby compatibility.

    [:octicons-arrow-right-24: Read more](overseerr-to-seerr.md)

-   **Recyclarr v7 → v8**

    ---

    The `radarr-k8s` and `sonarr-k8s` charms now ship Recyclarr 8, which
    renamed some of the TRaSH Guide templates accepted by the
    `trash-profiles` config. Most deployments need no action, but check
    before you refresh if you set that config explicitly.

    [:octicons-arrow-right-24: Read more](recyclarr-v8.md)

</div>
