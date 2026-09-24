<h1 class="header-with-badge">Setup <a href="https://github.com/charmarr/charmarr/actions/workflows/nightly-charmarr-track-1.yaml"><img src="https://img.shields.io/github/actions/workflow/status/charmarr/charmarr/nightly-charmarr-track-1.yaml?style=flat&label=nightly-tests&labelColor=000000" alt="Nightly Tests"></a></h1>

Get Charmarr running on your Kubernetes cluster in minutes.

!!! warning "track/1 is winding down"

    These docs describe **track/1**, the current stable track. It still receives
    fixes that keep the existing deployment working, but newly reported bugs and
    new features are not being addressed here.

    A stable **track/2** is coming soon. If you are deploying Charmarr for the
    first time, use the `latest/edge` channel rather than `1/stable`, so that you
    land on track/2 when it is released instead of migrating later.


<div class="grid cards" markdown>

-   **1. Prerequisites**

    ---

    Prepare your cluster and tools.

    [:octicons-arrow-right-24: Check requirements](prerequisites.md)

-   **2a. Quick Deploy**

    ---

    Pre-configured terraform modules.

    [:octicons-arrow-right-24: Get started](quickdeploy.md)

-   **2b. Manual Deploy**

    ---

    Juju CLI. More control, more fun.

    [:octicons-arrow-right-24: Learn more](manual.md)

-   **3. Post-Deploy**

    ---

    UI configurations in required apps.

    [:octicons-arrow-right-24: Final steps](post-deploy.md)

</div>
