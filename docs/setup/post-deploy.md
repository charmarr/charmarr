# Post-Deploy

Charmarr handles the backend wiring for all the cross-application configurations, but Plex and Seerr need one-time web UI user setup. Jellyfin needs neither, only a login.

!!! important
    The URLs below assume the default Traefik gateways. On a different ingress setup, read the addresses out of `juju status` for your own gateway applications.

## Watch the Deployment

Open a terminal and run:

```bash
juju status --integrations --watch 1s
```

!!! tip
    Keep this terminal open throughout the setup. It's the best way to monitor what's happening.

Watch Charmarr deploy and wire the applications together. Once settled, you should see something like this:

![Juju Status Pre-Websetup](../assets/screenshots/juju-status-pre-websetup.svg)

Plex and Seerr are in `waiting` status, waiting for user action. Everything else should be `active`.

---

## 1. Plex Setup

### Get Claim Token

1. Go to [plex.tv/claim](https://plex.tv/claim)
2. Copy the claim token

!!! note
    The claim token is stored as plain text, but that's fine because it's only valid for 4 minutes.

### Set Claim Token

```bash
juju config plex claim-token="claim-XXXXXXXXXXXXXXXXXXXX"
```

Plex should transition to `active` status.

!!! warning
    Wait 5-10 minutes before proceeding. Plex needs time to register the new server and propagate changes. If you're too fast, the server might not be registered yet.

### Open Plex UI

Get the Plex ingress IP from the `plex-ingress` message in `juju status`:

```
plex-ingress/0*    active    idle    10.1.239.97    Serving at 192.168.0.134
```

Open in browser:

```
http://192.168.0.134
```

### Complete Plex Setup

**Step 1:** Once the server is registered, you should see the welcome screen. Click **Got It!**

![Plex Step 1](../assets/screenshots/plex1.png)

**Step 2:** Enter a name for your server. Enable remote play if you want (2). Click **Next**. If you get a Plex Pass popup, you can safely close it.

![Plex Step 2](../assets/screenshots/plex2.png)

**Step 3:** Movie and TV libraries are already pre-configured by Charmarr (1, 2). The number of libraries here depends on your Radarr(s) and Sonarr(s). Click **Next**.

![Plex Step 3](../assets/screenshots/plex3.png)

<small>Curious how? See [Plex Charm Lifecycle](../charms/media-server.md#lifecycle).</small>

**Step 4:** Click **Done**.

![Plex Step 4](../assets/screenshots/plex4.png)

!!! warning
    Plex might not auto-scan libraries by default. See the [Plex docs on library scanning](https://support.plex.tv/articles/200289306-scanning-vs-refreshing-a-library/) to enable automatic refresh.

---

## 2. Jellyfin Setup

Skip this if you deployed Plex instead. Jellyfin is far less work: there is no claim token and no wizard, because the charm completes the startup wizard itself and creates the administrator account for you. Jellyfin never sits in `waiting`.

### Get the Initial Credentials

The charm stores them in a secret labelled `admin-credentials`:

```bash
juju show-secret --reveal admin-credentials
```

```yaml
da2qukfmp25c77r4nfeg:
  revision: 1
  owner: jellyfin
  description: Initial Jellyfin administrator credentials, ...
  label: admin-credentials
  content:
    password: <the generated password>
    username: charmarr
```

The charm owns a second secret labelled `api-key`, which holds the key it uses to manage libraries. You never need it.

### Open Jellyfin UI

Get the Jellyfin ingress IP from the `jellyfin-ingress` message in `juju status`:

```
jellyfin-ingress/0*    active    idle    10.1.239.104    Serving at 192.168.0.133
```

Open it in a browser and log in with those credentials. Your libraries are already there, created from your Radarr and Sonarr instances, so there is nothing left to configure.

!!! tip
    These are first-login credentials, not a live mirror of the account. Rename the account or change its password whenever you like: the charm authenticates with a server-wide API key that is not tied to the account, so library management and key rotation keep working. The secret keeps the original value, so note your new password somewhere.

---

## 3. Seerr Setup

How much work this is depends on which media server you deployed.

=== "Jellyfin"

    Nothing to do. The charm completes Seerr's setup wizard for you as soon as
    the two are related: it signs Seerr in to Jellyfin using the administrator
    account, enables every Jellyfin library for sync, and finalises the setup.
    Seerr comes up already configured.

    [Open the Seerr UI](#open-seerr-ui) and log in with the same Jellyfin
    credentials from [Jellyfin Setup](#2-jellyfin-setup), then skip ahead to
    [Verify Everything](#4-verify-everything).

    Your Seerr admin account is your Jellyfin admin account. Seerr does not
    store the password: it forwards each login to Jellyfin and matches you on
    your Jellyfin user ID. Change the password in Jellyfin and the new one
    works in Seerr immediately.

=== "Plex"

    Plex needs the wizard run by hand. The OAuth login is what creates your
    Seerr admin account, so the charm cannot do it for you, but Plex fills in
    the server details itself once you have signed in.

    Follow the steps below.

!!! info
    The `overseerr-k8s` charm is deprecated. If you deployed with
    `enable_overseerr = true` and need the Overseerr setup steps, see the
    [track 1 docs](https://charmarr.tv/en/track-1/setup/post-deploy/). To
    move an existing Overseerr deployment to Seerr, follow the
    [migration runbook](../migration/overseerr-to-seerr.md).

### Open Seerr UI

Get the Seerr ingress IP from the `seerr-ingress` message in `juju status`:

```
seerr-ingress/0*    active    idle    10.1.239.116    Serving at 192.168.0.132
```

Open in browser:

```
http://192.168.0.132
```

### Complete Seerr Setup (Plex only)

Skip this whole section if you deployed Jellyfin. The charm has already run it.

**Step 1:** Click **Configure Plex** to start the setup wizard.

![Seerr Step 1](../assets/screenshots/seerr1.png)

**Step 2:** Click **Login with Plex** and complete the OAuth flow.

![Seerr Step 2](../assets/screenshots/seerr2.png)

**Step 3:** Configure your Plex server:

1. Use the server dropdown to pick the Plex server you set up earlier (auto-populated via plex.tv).
2. Click **Save Changes**.
3. Enable sync for **Movies** and **TV Shows** under **Plex Libraries**.
4. Click **Continue**.

![Seerr Step 3](../assets/screenshots/overseerr2-seer3.png)

!!! warning
    Leave **Hostname or IP Address**, **Port**, and **Use SSL** at their
    default values - they're populated by Plex auto-discovery.

**Step 4:** Radarr and Sonarr settings may or may not be pre-filled, but it doesn't matter at this point. Do not add anything manually. Click **Finish Setup**.

![Seerr Step 4](../assets/screenshots/seerr4.png)

---

## 4. Verify Everything

Wait 5 minutes, then check `juju status`. All apps should be `active`:

![Juju Status Post-Websetup](../assets/screenshots/juju-status-post-websetup.svg)

In Seerr UI, go to:

<div class="nav-flow" markdown>
**Settings** :material-arrow-right: **Services**
</div>

Radarr(s) and Sonarr(s) should automatically appear. Charmarr added them for you.

<small>Curious how? See [Seerr Charm Lifecycle](../charms/media-requester.md#lifecycle).</small>

---

## 5. Add Indexers

Get the arr ingress IP from `juju status` and open Prowlarr:

```
http://ARR_INGRESS_IP/charmarr-prowlarr
```

Traefik serves each application under `/{model}-{app}`, so replace `charmarr` with your model name.

Add your indexers. The more the merrier.

### Usenet Setup (Optional)

If using usenet indexers, configure SABnzbd:

```
http://ARR_INGRESS_IP/charmarr-sabnzbd
```

Add a usenet server like [Frugal Usenet](https://frugalusenet.com/) or [Eweka](https://www.eweka.nl/).

### qBittorrent Access (Optional)

There's no mandatory need to access qBittorrent, but if you want to customize settings:

```
http://ARR_INGRESS_IP/charmarr-qbittorrent
```

Credentials are pre-configured by Charmarr. To retrieve them:

```bash
# List all secrets
juju secrets
# ID                    Name     Owner         Rotation  Revision  Last updated
# d5lvqs7mp25c7ffo3tv0  -        qbittorrent   monthly          1  8 hours ago

# Reveal the qbittorrent credentials (use the ID from above)
juju show-secret --reveal d5lvqs7mp25c7ffo3tv0
```

!!! note
    Charmarr [rotates credentials](../security/secrets.md) periodically. If login fails, grab the latest credentials using the commands above.

!!! warning
    The default account is Charmarr's account used for automation. Do not remove or change it.

---

## Done

Charmarr will continue to monitor, reconcile, and heal your stack.

Request a movie in Seerr, go prepare popcorn and grab a beer, come back and open Plex. Your movie should be ready. Mileage may vary based on internet speeds - you might even have time to prepare dinner.

!!! note
    This page covers Charmarr-specific configurations only. For general app configurations, which are not necessary for Charmarr as it does all the configurations for you, refer to each app's own documentation.

---

<div style="display: flex; justify-content: space-between" markdown>
<div markdown>
[:octicons-arrow-left-24: Quick Deploy](quickdeploy.md)
</div>
<div markdown>
</div>
</div>
