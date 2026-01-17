# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd config generation utilities."""

from io import BytesIO, StringIO
from typing import Any, cast

from configobj import ConfigObj

from _sabnzbd._constants import WEBUI_PORT

IniSection = dict[str, Any]


def build_sabnzbd_config(
    api_key: str, app_name: str = "sabnzbd-k8s", url_base: str | None = None
) -> str:
    """Build minimal sabnzbd.ini with API key, host/port, and URL base settings."""
    config: ConfigObj = ConfigObj()
    config["misc"] = {
        "api_key": api_key,
        "host": "0.0.0.0",
        "port": str(WEBUI_PORT),
        "host_whitelist": f"{app_name}, localhost",
    }
    if url_base:
        misc = cast(IniSection, config["misc"])
        misc["url_base"] = url_base

    output = BytesIO()
    config.write(output)
    return output.getvalue().decode("utf-8")


def _parse_config(content: str) -> ConfigObj:
    """Parse INI content into ConfigObj."""
    return ConfigObj(StringIO(content))


def _serialize_config(config: ConfigObj) -> str:
    """Serialize ConfigObj to string."""
    output = BytesIO()
    config.write(output)
    return output.getvalue().decode("utf-8")


def reconcile_sabnzbd_config(
    content: str | None,
    *,
    api_key: str,
    app_name: str,
    url_base: str | None = None,
) -> str:
    """Reconcile sabnzbd.ini idempotently, preserving user settings."""
    if content is None:
        return build_sabnzbd_config(api_key, app_name, url_base)

    config = _parse_config(content)

    if "misc" not in config:
        config["misc"] = {}

    misc = cast(IniSection, config["misc"])
    misc["api_key"] = api_key
    misc["host"] = "0.0.0.0"
    misc["port"] = str(WEBUI_PORT)
    misc["host_whitelist"] = f"{app_name}, localhost"

    if url_base:
        misc["url_base"] = url_base
    elif "url_base" in misc:
        del misc["url_base"]

    return _serialize_config(config)
