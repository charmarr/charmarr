# Overseerr → Seerr

Upstream Overseerr has merged with Jellyseerr into a new project: **Seerr**.
The `overseerr-k8s` charm is in maintenance mode and will be removed in a
future release. This guide walks you through moving your existing Overseerr
deployment to Seerr without losing requests, users, or settings.

What you get:

- Plex, Jellyfin, and Emby support (Overseerr is Plex-only)
- Active upstream - bug fixes, security patches, new features
- Identical Radarr/Sonarr integration via Juju relations
- All existing requests, users, and settings preserved

The migration is explicit and user-driven. Nothing changes until you run
the steps below. Seerr can run alongside Overseerr during cutover -
disable Overseerr only when you're satisfied Seerr is healthy.

---

## Before you start

- **Back up your Overseerr config PVC.** This is the migration's only
  destructive step; a snapshot or manual `kubectl cp` of `/config` to
  your laptop gives you a rollback path.
- **Confirm your `overseerr-k8s` revision includes the `export-config`
  action.** Run `juju run overseerr/0 export-config --help`. If the
  action is missing, refresh first:

    ```bash
    # latest (edge)
    juju refresh overseerr --channel=latest/edge

    # track 1 (stable)
    juju refresh overseerr --channel=1/stable
    ```

- **Identify pod and model names.** This guide uses `<model>` and
  `<overseerr-pod>` / `<seerr-pod>` placeholders. Substitute your
  actual values:

    ```bash
    juju models                    # find <model>
    juju status overseerr          # pod is <app>-<unit>, e.g. "overseerr-0"
    ```

!!! warning
    `juju scp` is broken for K8s sidecar containers on Juju 3.6.x - the
    tar stream silently drops mid-transfer and the destination file ends
    up empty even though the command exits 0. This guide uses
    `kubectl cp` for all file copies.

---

## 1. Export the Overseerr config

```bash
juju run overseerr/0 export-config
```

The action tars `/config` (excluding `logs/`, `cache/`, `*.tmp`) to
`/config/overseerr-export.tgz` inside the workload container. Output:

```yaml
copy-command: |
  kubectl -n <model> cp -c overseerr <overseerr-pod>:/config/overseerr-export.tgz
    ./overseerr-export.tgz
path: /config/overseerr-export.tgz
sha256: 5d1b46df5cc7a7ecd8b8922d35c0891ddc8646edf3f9852f1ecb5c77657d57f2
size: "8333"
```

Save the `sha256` - you'll use it to verify the transfer.

## 2. Pull the tarball

```bash
kubectl -n <model> cp -c overseerr <overseerr-pod>:/config/overseerr-export.tgz ./export.tgz
sha256sum ./export.tgz
# should match the sha256 from step 1
```

## 3. Enable Seerr alongside Overseerr

=== "Quick Deploy"

    Add `enable_seerr = true` to your `main.tf`:

    ```hcl
    module "charmarr" {
      # ... your existing config ...

      enable_overseerr = true   # keep running until cutover
      enable_seerr     = true   # new
    }
    ```

    Apply:

    ```bash
    terraform apply
    ```

    The bundle deploys `seerr-k8s` and creates all relations
    (Radarr/Sonarr, Plex, ingress, service-mesh). Wait for the Seerr
    unit to reach `waiting: Complete setup in web UI` - that's the
    post-first-start state.

    !!! warning
        Do not complete the web UI setup yet - the next step will
        overwrite the config.

=== "Manual Deploy"

    ```bash
    juju deploy seerr-k8s --trust --channel=latest/edge seerr

    juju integrate seerr:media-manager radarr:media-manager
    juju integrate seerr:media-manager sonarr:media-manager
    juju integrate seerr:media-server  plex:media-server

    # optional: dedicated ingress (mirrors your existing overseerr-ingress)
    juju deploy istio-ingress-k8s --trust --channel=dev/edge seerr-ingress
    juju integrate seerr:istio-ingress-route seerr-ingress:istio-ingress-route

    # optional: service mesh
    juju integrate seerr:service-mesh beacon:service-mesh
    ```

    Wait for `juju status seerr` to show
    `waiting: Complete setup in web UI`. Don't complete the wizard.

## 4. Push the tarball to Seerr

```bash
kubectl -n <model> cp -c seerr ./export.tgz <seerr-pod>:/app/config/import.tgz
```

## 5. Run `import-config`

```bash
juju run seerr/0 import-config \
  path=/app/config/import.tgz \
  sha256=<sha256-from-step-1>
```

The action stops the Seerr workload, wipes `/app/config`, extracts the
tarball, fixes ownership, and replans. On next start, Seerr's upstream
auto-migration rewrites the Overseerr schema into Seerr's format. A
backup of the original `settings.json` is preserved inside the workload
container as `/app/config/settings.old.json`.

## 6. Verify

```bash
juju status seerr
```

Once Seerr finishes its first start with the imported config, the unit
will sit at `waiting: Complete setup in web UI` again. This is normal -
Seerr regenerates session secrets on the schema upgrade, so you need to
re-validate the Plex OAuth in the web UI.

Sanity-check the data:

- Open the Seerr UI via your ingress (or port-forward).
- Sign in with your Plex account.
- **Settings → Services** - Radarr and Sonarr should be pre-configured.
- **Users** - existing accounts should be listed.
- **Requests** - history should be intact.

## 7. Decommission Overseerr

Only do this once you've verified Seerr is healthy and serving requests.

=== "Quick Deploy"

    Set `enable_overseerr = false` in your `main.tf`:

    ```hcl
    module "charmarr" {
      # ... your existing config ...

      enable_overseerr = false  # decommission
      enable_seerr     = true
    }
    ```

    ```bash
    terraform apply
    ```

    The bundle removes the `overseerr` app, the `overseerr-ingress`
    helper, and all their relations.

=== "Manual Deploy"

    ```bash
    juju remove-application overseerr
    juju remove-application overseerr-ingress   # if you ran a dedicated ingress
    ```

The Overseerr PVC will be released. Hang onto your backup tarball for a
few days as insurance.

---

## Troubleshooting

??? question "`import-config` fails with `Tarball not found at /app/config/import.tgz`"
    The `kubectl cp` in step 4 didn't land the file. Verify:

    ```bash
    kubectl -n <model> exec <seerr-pod> -c seerr -- ls -la /app/config/import.tgz
    ```

    If missing, re-run the `kubectl cp`. Make sure you pass `-c seerr` -
    without it, `kubectl cp` copies into the charm container, not the
    workload.

??? question "`import-config` fails with `sha256 mismatch`"
    The tarball was corrupted in transit, or you passed the wrong
    checksum. Re-run `export-config`, re-copy, and pass the new checksum.
    The `sha256` parameter is optional - you can omit it to skip
    verification, but it's strongly recommended.

??? question "Seerr won't start after import"
    Check the workload logs:

    ```bash
    kubectl -n <model> logs <seerr-pod> -c seerr
    ```

    Common causes: a corrupt database file in the tarball, or filesystem
    ownership wrong. The `import-config` action runs
    `chown -R 1000:1000 /app/config`, but if your storage backend has
    restrictive permissions you may need to fix them manually.

??? question "I lost data - how do I roll back?"
    Stop Seerr (`enable_seerr = false` + `terraform apply`, or
    `juju remove-application seerr`), restore the Overseerr PVC from
    your backup if it was destroyed, and you're back where you started.
    Because the migration is action-driven and Overseerr is only read
    from (never modified), rolling back is just "use the backup."

??? question "Can I migrate without downtime?"
    Not cleanly. Both apps would need to share Plex/Radarr/Sonarr state,
    and Seerr's first-start auto-migration is destructive to its own
    `/app/config`. Plan a brief maintenance window. The actual data
    transfer takes seconds; most of the time is Seerr restarting.

---

## What changes after migration

| | Overseerr | Seerr |
|---|---|---|
| OCI image | `lscr.io/linuxserver/overseerr` | `ghcr.io/seerr-team/seerr` |
| Config path | `/config` | `/app/config` |
| Port | 5055 | 5055 |
| Media servers | Plex only | Plex, Jellyfin, Emby |
| API endpoints | `/api/v1/...` | `/api/v1/...` (compatible) |
| Settings file | `settings.json` | `settings.json` (+ `settings.old.json` post-migration) |
| Relations on the charm | `media-manager`, `media-server`, `istio-ingress-route`, … | same |
| Juju app name | `overseerr` (convention) | `seerr` (convention) |

The `/api/v1/` API is backwards-compatible - any external integrations
(mobile apps, browser extensions, third-party tools) keep working with
the new endpoint URL.
