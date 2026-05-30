# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Kubernetes resource quantity parsing."""

import re

_SUFFIXES: dict[str, int] = {
    "": 1,
    "k": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
    "P": 1000**5,
    "E": 1000**6,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "Pi": 1024**5,
    "Ei": 1024**6,
}

_QUANTITY_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGTPE]i?|k)?\s*$")


def parse_quantity_to_bytes(value: str) -> int | None:
    """Parse a K8s resource quantity string (e.g. "100Gi", "1.5Ti") to bytes.

    Returns None if the input is empty, malformed, or uses an unsupported
    suffix (e.g. milli "m", exponent notation). Per the Kubernetes API,
    binary suffixes (Ki/Mi/Gi/Ti) and decimal suffixes (k/M/G/T) are both
    valid for storage requests.
    """
    if not value:
        return None
    match = _QUANTITY_RE.match(value)
    if not match:
        return None
    number, suffix = match.groups()
    multiplier = _SUFFIXES.get(suffix or "")
    if multiplier is None:
        return None
    return int(float(number) * multiplier)
