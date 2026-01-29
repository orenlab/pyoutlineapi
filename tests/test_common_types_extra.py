from __future__ import annotations

import pytest

from pyoutlineapi import common_types
from pyoutlineapi.common_types import (
    Constants,
    SSRFProtection,
    Validators,
    mask_sensitive_data,
    validate_snapshot_size,
)


def test_validate_since_accepts_relative_and_iso():
    assert Validators.validate_since("24h") == "24h"
    assert Validators.validate_since("2024-01-01T00:00:00Z") == "2024-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        Validators.validate_since("invalid")


def test_validate_key_id_invalid_characters():
    assert Validators.validate_key_id("key_123") == "key_123"
    with pytest.raises(ValueError):
        Validators.validate_key_id("bad%2Fkey")


def test_sanitize_url_for_logging_invalid(monkeypatch):
    def bad_parse(_url: str):  # type: ignore[no-untyped-def]
        raise ValueError("bad")

    monkeypatch.setattr(common_types, "urlparse", bad_parse)
    assert Validators.sanitize_url_for_logging("http://example.com") == "***INVALID_URL***"


def test_sanitize_endpoint_for_logging_empty():
    assert Validators.sanitize_endpoint_for_logging("") == "***EMPTY***"


def test_mask_sensitive_data_max_depth():
    data: dict[str, object] = {}
    current = data
    for _ in range(Constants.MAX_RECURSION_DEPTH + 2):
        current["next"] = {}
        current = current["next"]  # type: ignore[assignment]

    masked = mask_sensitive_data(data)
    # Walk down until error marker appears
    cursor = masked
    found = False
    while isinstance(cursor, dict) and "next" in cursor:
        cursor = cursor["next"]  # type: ignore[assignment]
        if isinstance(cursor, dict) and cursor.get("_error") == "Max recursion depth exceeded":
            found = True
            break
    assert found is True


def test_mask_sensitive_data_list_without_dicts():
    data = {"items": ["a", 1, None]}
    masked = mask_sensitive_data(data)
    assert masked["items"] == ["a", 1, None]


def test_validate_snapshot_size_limit(monkeypatch):
    monkeypatch.setattr(Constants, "MAX_SNAPSHOT_SIZE_MB", 0)
    with pytest.raises(ValueError):
        validate_snapshot_size({"x": "y"})


def test_resolve_hostname_invalid_entries(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [(None, None, None, None, ("not-an-ip", 0))]

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        SSRFProtection._resolve_hostname("example.com")

    with pytest.raises(ValueError):
        SSRFProtection._resolve_hostname_uncached("example.com")


def test_is_blocked_hostname_allows_localhost():
    assert SSRFProtection.is_blocked_hostname("localhost") is False
    assert SSRFProtection.is_blocked_hostname_uncached("localhost") is False
