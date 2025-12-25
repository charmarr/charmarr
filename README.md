<p align="center">
  <img src="assets/charmarr-charmarr.png" width="350" alt="Charmarr">
</p>

<h1 align="center">Charmarr Charms</h1>

<p align="center">
  <a href="https://github.com/charmarr/charmarr/actions/workflows/ci.yaml"><img src="https://github.com/charmarr/charmarr/actions/workflows/ci.yaml/badge.svg" alt="CI"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
  <a href="https://github.com/charmarr/charmarr/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="License"></a>
</p>

## Charms

| Charm | Description | CharmHub |
|-------|-------------|----------|
| **charmarr-storage-k8s** | Shared PVC provider for hardlinks across media apps | [![CharmHub](https://charmhub.io/charmarr-storage-k8s/badge.svg)](https://charmhub.io/charmarr-storage-k8s) |
| **charmarr-multimeter-k8s** | Test utility charm for validating interface providers | [![CharmHub](https://charmhub.io/charmarr-multimeter-k8s/badge.svg)](https://charmhub.io/charmarr-multimeter-k8s) |
| **gluetun-k8s** | VPN gateway with pod-gateway for routing client traffic | [![CharmHub](https://charmhub.io/gluetun-k8s/badge.svg)](https://charmhub.io/gluetun-k8s) |

## Development

```bash
cd charms/charmarr-storage-k8s
uv venv && source .venv/bin/activate
uv sync
tox
```

<!-- TODO: expand this README -->

## License

AGPL-3.0-or-later
