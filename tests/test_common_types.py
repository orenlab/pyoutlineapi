from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from pyoutlineapi import common_types
from pyoutlineapi.common_types import (
    Constants,
    CredentialSanitizer,
    SSRFProtection,
    SecureIDGenerator,
    Validators,
    build_config_overrides,
    merge_config_kwargs,
    is_json_serializable,
    is_valid_bytes,
    is_valid_port,
    mask_sensitive_data,
    validate_snapshot_size,
)
from pyoutlineapi.models import DataLimit


def test_is_valid_port_and_bytes():
    assert is_valid_port(1) is True
    assert is_valid_port(65535) is True
    assert is_valid_port(0) is False
    assert is_valid_bytes(0) is True
    assert is_valid_bytes(-1) is False


def test_ssrf_protection_blocked_private_ip():
    assert SSRFProtection.is_blocked_ip("10.0.0.1") is True
    assert SSRFProtection.is_blocked_ip("127.0.0.1") is False
    assert SSRFProtection.is_blocked_ip("example.com") is False


def test_credential_sanitizer_patterns():
    text = "password=secret api_key=ABCDEFGH1234567890TOKEN"
    sanitized = CredentialSanitizer.sanitize(text)
    assert "***PASSWORD***" in sanitized
    assert "***API_KEY***" in sanitized
    assert CredentialSanitizer.sanitize("") == ""


def test_mask_sensitive_data_nested():
    data = {"token": "abc", "nested": {"password": "secret"}, "ok": 1}
    masked = mask_sensitive_data(data)
    assert masked["token"] == "***MASKED***"
    assert masked["nested"]["password"] == "***MASKED***"
    assert masked["ok"] == 1


def test_mask_sensitive_data_list_branch():
    data = {"items": [{"token": "x"}, {"ok": 1}], "other": 1}
    masked = mask_sensitive_data(data)
    assert masked["items"][0]["token"] == "***MASKED***"


def test_mask_sensitive_data_list_with_non_dict_items():
    data = {"items": [{"token": "x"}, "plain", 5]}
    masked = mask_sensitive_data(data)
    assert masked["items"][0]["token"] == "***MASKED***"
    assert masked["items"][1] == "plain"
    assert masked["items"][2] == 5


def test_validators_basic():
    assert Validators.validate_port(8080) == 8080
    with pytest.raises(ValueError):
        Validators.validate_port(0)

    assert Validators.validate_name(" Test ") == "Test"
    with pytest.raises(ValueError):
        Validators.validate_name(" ")
    with pytest.raises(ValueError):
        Validators.validate_name("x" * (Constants.MAX_NAME_LENGTH + 1))

    from pydantic import SecretStr

    secret = Validators.validate_cert_fingerprint(
        SecretStr("a" * Constants.CERT_FINGERPRINT_LENGTH)
    )
    assert secret.get_secret_value() == "a" * Constants.CERT_FINGERPRINT_LENGTH

    from pydantic import SecretStr

    with pytest.raises(ValueError):
        Validators.validate_cert_fingerprint(SecretStr("bad"))
    with pytest.raises(ValueError):
        Validators.validate_cert_fingerprint(SecretStr(""))


def test_validate_url_private_networks():
    url = "https://10.0.0.1:1234/secret"
    assert Validators.validate_url(url, allow_private_networks=True) == url
    with pytest.raises(ValueError):
        Validators.validate_url(url, allow_private_networks=False)


def test_validate_url_invalid_cases():
    with pytest.raises(ValueError):
        Validators.validate_url("")
    with pytest.raises(ValueError):
        Validators.validate_url("http://")
    with pytest.raises(ValueError):
        Validators.validate_url("http://example.com/\x00")
    long_url = "http://example.com/" + ("a" * (Constants.MAX_URL_LENGTH + 1))
    with pytest.raises(ValueError):
        Validators.validate_url(long_url)


def test_validate_url_strict_ssrf_blocks_private(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [(None, None, None, None, ("10.0.0.5", 0))]

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        Validators.validate_url(
            "https://example.com",
            allow_private_networks=False,
            resolve_dns=True,
        )


def test_validate_url_strict_ssrf_allows_public(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [(None, None, None, None, ("1.1.1.1", 0))]

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    url = Validators.validate_url(
        "https://example.com",
        allow_private_networks=False,
        resolve_dns=True,
    )
    assert url.startswith("https://example.com")


def test_validate_url_strict_ssrf_rebinding_guard(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [
            (None, None, None, None, ("1.1.1.1", 0)),
            (None, None, None, None, ("10.0.0.9", 0)),
        ]

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        Validators.validate_url(
            "https://example.com",
            allow_private_networks=False,
            resolve_dns=True,
        )


def test_validate_url_strict_ssrf_blocks_private_ipv6(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [(None, None, None, None, ("fd00::1", 0, 0, 0))]

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        Validators.validate_url(
            "https://example.com",
            allow_private_networks=False,
            resolve_dns=True,
        )


def test_validate_url_strict_ssrf_allows_public_ipv6(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [(None, None, None, None, ("2606:4700:4700::1111", 0, 0, 0))]

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    url = Validators.validate_url(
        "https://example.com",
        allow_private_networks=False,
        resolve_dns=True,
    )
    assert url.startswith("https://example.com")


def test_validate_url_strict_ssrf_blocks_mixed_ipv6(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [
            (None, None, None, None, ("2606:4700:4700::1111", 0, 0, 0)),
            (None, None, None, None, ("fd00::2", 0, 0, 0)),
        ]

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        Validators.validate_url(
            "https://example.com",
            allow_private_networks=False,
            resolve_dns=True,
        )


def test_validate_url_strict_ssrf_resolution_error(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise common_types.socket.gaierror("boom")

    SSRFProtection._resolve_hostname.cache_clear()
    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        Validators.validate_url(
            "https://example.com",
            allow_private_networks=False,
            resolve_dns=True,
        )


def test_validate_url_blocks_localhost_when_private_disallowed():
    with pytest.raises(ValueError):
        Validators.validate_url(
            "http://localhost:1234",
            allow_private_networks=False,
            resolve_dns=False,
        )


def test_is_blocked_hostname_uncached_blocks_private(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [(None, None, None, None, ("10.0.0.8", 0))]

    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    assert SSRFProtection.is_blocked_hostname_uncached("example.com") is True


def test_is_blocked_hostname_uncached_allows_localhost():
    assert SSRFProtection.is_blocked_hostname_uncached("localhost") is False


def test_resolve_hostname_uncached_resolution_error(monkeypatch):
    def fake_getaddrinfo(_host, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise common_types.socket.gaierror("boom")

    monkeypatch.setattr(common_types.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        SSRFProtection.is_blocked_hostname_uncached("example.com")


def test_validate_non_negative_and_since():
    assert Validators.validate_non_negative(10, "limit") == 10
    assert Validators.validate_non_negative(DataLimit(bytes=5), "limit") == 5

    now_iso = datetime.now(timezone.utc).isoformat()
    assert Validators.validate_since(now_iso) == now_iso
    assert Validators.validate_since("1h") == "1h"
    with pytest.raises(ValueError):
        Validators.validate_since("")
    with pytest.raises(ValueError):
        Validators.validate_since("not-a-time")
    with pytest.raises(ValueError):
        Validators.validate_non_negative(-1, "limit")


def test_build_config_overrides_and_json_serializable():
    overrides = build_config_overrides(timeout=10, enable_logging=True, foo=1)  # type: ignore[arg-type]
    assert overrides["timeout"] == 10
    assert overrides["enable_logging"] is True
    assert "foo" not in overrides

    merged = merge_config_kwargs({"a": 1}, {"timeout": 5})
    assert merged["a"] == 1
    assert merged["timeout"] == 5

    assert is_json_serializable({"a": 1, "b": [1, 2]}) is True
    assert is_json_serializable({"t": time.time(), "f": object()}) is False


def test_validate_snapshot_size_ok():
    validate_snapshot_size({"a": 1, "b": {"c": 2}})


def test_sanitize_url_and_endpoint():
    url = "https://example.com/secret/path"
    assert Validators.sanitize_url_for_logging(url) == "https://example.com/***"
    assert Validators.sanitize_endpoint_for_logging("") == "***EMPTY***"
    assert Validators.sanitize_endpoint_for_logging("a" * 30) == "***"


def test_validate_snapshot_size_error(monkeypatch):
    def fake_getsizeof(_):  # type: ignore[no-untyped-def]
        return (Constants.MAX_SNAPSHOT_SIZE_MB * 1024 * 1024) + 1

    monkeypatch.setattr("sys.getsizeof", fake_getsizeof)
    with pytest.raises(ValueError):
        validate_snapshot_size({"data": "x"})


def test_mask_sensitive_depth_limit():
    nested: dict[str, object] = {}
    current = nested
    for _ in range(Constants.MAX_RECURSION_DEPTH + 2):
        new: dict[str, object] = {}
        current["child"] = new
        current = new
    masked = mask_sensitive_data(nested)
    # Walk down to find the depth error marker
    current = masked
    found_error = False
    for _ in range(Constants.MAX_RECURSION_DEPTH + 3):
        if isinstance(current, dict) and "_error" in current:
            found_error = True
            break
        current = current.get("child", {}) if isinstance(current, dict) else {}
    assert found_error is True


def test_secure_id_generator():
    cid = SecureIDGenerator.generate_correlation_id()
    assert isinstance(cid, str)
    assert len(cid) >= 16

    token = SecureIDGenerator.generate_request_id()
    assert isinstance(token, str)
    assert len(token) >= 16


def test_validate_string_not_empty():
    assert Validators.validate_string_not_empty("x", "field") == "x"
    with pytest.raises(ValueError):
        Validators.validate_string_not_empty("", "field")


def test_validate_key_id_and_sanitize_url_error():
    assert Validators.validate_key_id("key-1") == "key-1"
    with pytest.raises(ValueError):
        Validators.validate_key_id("bad id")
    with pytest.raises(ValueError):
        Validators.validate_key_id("bad/../id")
    with pytest.raises(ValueError):
        Validators.validate_key_id("bad\x00id")
    with pytest.raises(ValueError):
        Validators.validate_key_id("a" * (Constants.MAX_KEY_ID_LENGTH + 1))

    assert Validators.sanitize_url_for_logging("::bad") == ":///***"


def test_sanitize_url_for_logging_exception(monkeypatch):
    def boom(_url):  # type: ignore[no-untyped-def]
        raise ValueError("boom")

    monkeypatch.setattr("pyoutlineapi.common_types.urlparse", boom)
    assert (
        Validators.sanitize_url_for_logging("http://example.com") == "***INVALID_URL***"
    )
