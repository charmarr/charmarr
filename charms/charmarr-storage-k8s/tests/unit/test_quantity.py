# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for the K8s quantity parser."""

import pytest

from _storage import parse_quantity_to_bytes


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("100Gi", 100 * 1024**3),
        ("1.5Ti", int(1.5 * 1024**4)),
        ("512Mi", 512 * 1024**2),
        ("100G", 100 * 1000**3),
        ("1k", 1000),
        ("1000", 1000),  # no suffix means raw bytes
    ],
)
def test_parse_valid_quantities(value: str, expected: int):
    assert parse_quantity_to_bytes(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",
        "100Xi",  # bogus suffix
        "1.5.6Gi",  # malformed number
        "100m",  # milli is valid k8s syntax but not a storage suffix we support
    ],
)
def test_parse_invalid_or_unsupported_quantities(value: str):
    assert parse_quantity_to_bytes(value) is None
