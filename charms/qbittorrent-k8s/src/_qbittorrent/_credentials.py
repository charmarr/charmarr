# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""qBittorrent credential generation utilities.

qBittorrent stores WebUI credentials in qBittorrent.conf as PBKDF2-SHA512 hash:
  WebUI\\Password_PBKDF2="@ByteArray(SALT:HASH)"

Where:
- SALT: 16 random bytes, base64 encoded
- HASH: PBKDF2-SHA512(password, salt, iterations=100000), base64 encoded
"""

import base64
import hashlib
import re
import secrets

from _qbittorrent._constants import PASSWORD_BYTES, PBKDF2_ITERATIONS, SALT_BYTES


def generate_password(length: int = PASSWORD_BYTES) -> str:
    """Generate a cryptographically secure password."""
    return secrets.token_urlsafe(length)


def compute_pbkdf2_hash(password: str) -> str:
    """Compute PBKDF2-SHA512 hash in qBittorrent format.

    Returns:
        String in format "@ByteArray(SALT_B64:HASH_B64)"
    """
    salt = secrets.token_bytes(SALT_BYTES)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha512",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(hash_bytes).decode("ascii")
    return f"@ByteArray({salt_b64}:{hash_b64})"


def build_qbittorrent_config(username: str, password_hash: str) -> str:
    """Build minimal qBittorrent.conf with WebUI credentials.

    This config is written BEFORE the first Pebble start so qBittorrent
    reads it on startup. Only includes auth settings; qBittorrent fills
    in defaults for everything else.

    LocalHostAuth=false bypasses auth for localhost (Pebble health check).
    """
    return f"""[Preferences]
WebUI\\Username={username}
WebUI\\Password_PBKDF2={password_hash}
WebUI\\LocalHostAuth=false
WebUI\\CSRFProtection=false
WebUI\\HostHeaderValidation=false
"""


def _set_ini_value(content: str, section: str, key: str, value: str) -> str:
    """Set or update an INI key in a section."""
    escaped_key = re.escape(key)
    pattern = rf"^({escaped_key})=.*$"

    if re.search(pattern, content, re.MULTILINE):
        return re.sub(pattern, rf"\1={value}", content, flags=re.MULTILINE)

    section_pattern = rf"(\[{re.escape(section)}\])"
    if re.search(section_pattern, content):
        return re.sub(section_pattern, rf"\1\n{key}={value}", content)

    return f"[{section}]\n{key}={value}\n" + content


def reconcile_qbittorrent_config(
    content: str | None,
    *,
    username: str,
    password_hash: str,
) -> str:
    """Reconcile qBittorrent.conf idempotently, preserving user settings."""
    if content is None:
        return build_qbittorrent_config(username, password_hash)

    managed_keys = {
        "WebUI\\\\Username": username,
        "WebUI\\\\Password_PBKDF2": password_hash,
        "WebUI\\\\LocalHostAuth": "false",
        "WebUI\\\\CSRFProtection": "false",
        "WebUI\\\\HostHeaderValidation": "false",
    }

    for key, value in managed_keys.items():
        content = _set_ini_value(content, "Preferences", key, value)

    return content
