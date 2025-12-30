# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""SABnzbd config generation utilities."""

import re

from _sabnzbd._constants import WEBUI_PORT


def build_sabnzbd_config(
    api_key: str, app_name: str = "sabnzbd-k8s", url_base: str | None = None
) -> str:
    """Build minimal sabnzbd.ini with API key, host/port, and URL base settings."""
    url_base_line = f"url_base = {url_base}\n" if url_base else ""
    return f"""[misc]
api_key = {api_key}
host = 0.0.0.0
port = {WEBUI_PORT}
host_whitelist = {app_name}, localhost
{url_base_line}"""


def _set_ini_value(content: str, section: str, key: str, value: str) -> str:
    """Set or update an INI key in a section."""
    pattern = rf"^({re.escape(key)}) = .*$"

    if re.search(pattern, content, re.MULTILINE):
        return re.sub(pattern, rf"\1 = {value}", content, flags=re.MULTILINE)

    section_pattern = rf"(\[{re.escape(section)}\])"
    if re.search(section_pattern, content):
        return re.sub(section_pattern, rf"\1\n{key} = {value}", content)

    return f"[{section}]\n{key} = {value}\n" + content


def _remove_ini_value(content: str, key: str) -> str:
    """Remove an INI key if it exists."""
    return re.sub(rf"^{re.escape(key)} = .*\n?", "", content, flags=re.MULTILINE)


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

    content = _set_ini_value(content, "misc", "api_key", api_key)
    content = _set_ini_value(content, "misc", "host", "0.0.0.0")
    content = _set_ini_value(content, "misc", "port", str(WEBUI_PORT))
    content = _set_ini_value(content, "misc", "host_whitelist", f"{app_name}, localhost")

    if url_base:
        content = _set_ini_value(content, "misc", "url_base", url_base)
    else:
        content = _remove_ini_value(content, "url_base")

    return content
