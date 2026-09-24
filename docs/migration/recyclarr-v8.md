# Recyclarr v7 → v8

The `radarr-k8s` and `sonarr-k8s` charms now ship Recyclarr 8. Recyclarr v8
restructured how TRaSH Guide profiles are referenced, and a few of the template
names accepted by the `trash-profiles` config no longer exist upstream.

Most deployments need no action. You only need to change something if you set
`trash-profiles` explicitly to a name that v8 removed.

## Do I need to do anything?

Check what each of your instances is configured with:

```bash
juju config radarr trash-profiles
juju config sonarr trash-profiles
```

- **Empty output:** nothing to do. The charm picks a default for you, and the
  defaults have been updated to names that exist in v8.
- **A value listed under "Renamed templates" below:** update it before you
  refresh, otherwise the profile sync fails.
- **Any other value:** confirm it appears in the charm's `trash-profiles`
  config description, which lists the templates valid for that charm.

## Renamed templates

| Old value | Radarr | Sonarr |
|-----------|--------|--------|
| `anime` | `anime-remux-1080p` | `anime-remux-1080p` |
| `uhd-bluray-web` | unchanged | `web-2160p` |

TRaSH Guides names Sonarr's profiles differently from Radarr's, so a value that
is valid for one charm is not necessarily valid for the other. `uhd-bluray-web`
remains correct for Radarr and has no Sonarr equivalent under that name.

To update:

```bash
juju config radarr trash-profiles=anime-remux-1080p
juju config sonarr trash-profiles=web-2160p
```

## Changed defaults

If you leave `trash-profiles` empty, the charm chooses a default from the
content variant. Those defaults changed:

| Variant | Charm | Before | After |
|---------|-------|--------|-------|
| `4k` | radarr | `uhd-bluray-web` | `uhd-bluray-web` |
| `4k` | sonarr | `uhd-bluray-web` | `web-2160p` |
| `anime` | radarr | `anime` | `anime-remux-1080p` |
| `anime` | sonarr | `anime` | `anime-remux-1080p` |
| `standard` | both | none | none |

The Sonarr rows are a correction as well as a rename. The previous defaults
named Radarr templates, which Sonarr never had, so the `4k` and `anime`
variants of `sonarr-k8s` did not sync a profile at all.

## What happens on refresh

The charm syncs profiles when it reconciles, so a refresh applies the new
templates without further action. If a template name is invalid, the sync
fails and the charm reports the error in its status rather than silently
skipping the profile.

Recyclarr v8 also changes how custom formats are grouped upstream. Scores and
custom formats that you adjusted by hand in Radarr or Sonarr may be reset to
the guide's recommended values on the next sync, which was already true of
v7 syncs but affects a wider set of formats in v8.
