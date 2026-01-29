"""PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

from __future__ import annotations

import ipaddress
import logging
import re
import secrets
import socket
import sys
import time
import urllib.parse
from datetime import datetime
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Final,
    TypeAlias,
    TypedDict,
    TypeGuard,
    Union,
)
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr

if TYPE_CHECKING:
    from .models import DataLimit

if TYPE_CHECKING:
    from collections.abc import Mapping

# ===== Type Aliases - Core Types =====

Port: TypeAlias = Annotated[
    int, Field(ge=1, le=65535, description="Port number (1-65535)")
]
Bytes: TypeAlias = Annotated[int, Field(ge=0, description="Size in bytes")]

TimestampMs: TypeAlias = Annotated[
    int, Field(ge=0, description="Unix timestamp in milliseconds")
]
TimestampSec: TypeAlias = Annotated[
    int, Field(ge=0, description="Unix timestamp in seconds")
]

# Backward compatibility
Timestamp: TypeAlias = TimestampMs

# ===== Type Aliases - JSON and API Types =====

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = Union[JsonPrimitive, "JsonDict", "JsonList"]
JsonDict: TypeAlias = dict[str, JsonValue]
JsonList: TypeAlias = list[JsonValue]
JsonPayload: TypeAlias = JsonDict | JsonList | None
ResponseData: TypeAlias = JsonDict
QueryParams: TypeAlias = dict[str, str | int | float | bool]

# ===== Type Aliases - Common Structures =====

ChecksDict: TypeAlias = dict[str, dict[str, Any]]
BytesPerUserDict: TypeAlias = dict[str, int]
AuditDetails: TypeAlias = dict[str, str | int | float | bool]
MetricsTags: TypeAlias = dict[str, str]


# ===== Constants =====


class Constants:
    """Application-wide constants with security limits."""

    # Port constraints
    MIN_PORT: Final[int] = 1
    MAX_PORT: Final[int] = 65535

    # Length limits
    MAX_NAME_LENGTH: Final[int] = 255
    CERT_FINGERPRINT_LENGTH: Final[int] = 64
    MAX_KEY_ID_LENGTH: Final[int] = 255
    MAX_URL_LENGTH: Final[int] = 2048

    # Network defaults
    DEFAULT_TIMEOUT: Final[int] = 10
    DEFAULT_RETRY_ATTEMPTS: Final[int] = 2
    DEFAULT_MIN_CONNECTIONS: Final[int] = 1
    DEFAULT_MAX_CONNECTIONS: Final[int] = 100
    DEFAULT_RETRY_DELAY: Final[float] = 1.0
    DEFAULT_MIN_TIMEOUT: Final[int] = 1
    DEFAULT_MAX_TIMEOUT: Final[int] = 300
    DEFAULT_USER_AGENT: Final[str] = "PyOutlineAPI/0.4.0"
    _MIN_RATE_LIMIT: Final[int] = 1
    _MAX_RATE_LIMIT: Final[int] = 1000
    _SAFETY_MARGIN: Final[float] = 10.0

    # Resource limits
    MAX_RECURSION_DEPTH: Final[int] = 10
    MAX_SNAPSHOT_SIZE_MB: Final[int] = 10

    # HTTP retry codes
    RETRY_STATUS_CODES: Final[frozenset[int]] = frozenset(
        {408, 429, 500, 502, 503, 504}
    )

    # Logging levels
    LOG_LEVEL_DEBUG: Final[int] = logging.DEBUG
    LOG_LEVEL_INFO: Final[int] = logging.INFO
    LOG_LEVEL_WARNING: Final[int] = logging.WARNING
    LOG_LEVEL_ERROR: Final[int] = logging.ERROR

    # ===== Security limits =====

    # Response size protection (DoS prevention)
    MAX_RESPONSE_SIZE: Final[int] = 10 * 1024 * 1024  # 10 MB
    MAX_RESPONSE_CHUNK_SIZE: Final[int] = 8192  # 8 KB chunks

    # Rate limiting defaults
    DEFAULT_RATE_LIMIT_RPS: Final[float] = 100.0  # Requests per second
    DEFAULT_RATE_LIMIT_BURST: Final[int] = 200  # Burst capacity
    DEFAULT_RATE_LIMIT: Final[int] = 100  # Concurrent requests

    # Connection limits
    MAX_CONNECTIONS_PER_HOST: Final[int] = 50
    DNS_CACHE_TTL: Final[int] = 300  # 5 minutes

    # Timeout strategies
    TIMEOUT_WARNING_RATIO: Final[float] = 0.8  # Warn at 80% of timeout
    MAX_TIMEOUT: Final[int] = 300  # 5 minutes absolute max


# ===== SSRF Protection (HIGH-002) =====


class SSRFProtection:
    """SSRF protection with blocked IP ranges."""

    # Private and special-use IP ranges to block
    BLOCKED_IP_RANGES: Final[list[ipaddress.IPv4Network | ipaddress.IPv6Network]] = [
        ipaddress.ip_network("0.0.0.0/8"),  # Current network
        ipaddress.ip_network("10.0.0.0/8"),  # Private
        ipaddress.ip_network("127.0.0.0/8"),  # Loopback
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local
        ipaddress.ip_network("172.16.0.0/12"),  # Private
        ipaddress.ip_network("192.168.0.0/16"),  # Private
        ipaddress.ip_network("224.0.0.0/4"),  # Multicast
        ipaddress.ip_network("240.0.0.0/4"),  # Reserved
        ipaddress.ip_network("::1/128"),  # IPv6 loopback
        ipaddress.ip_network("fc00::/7"),  # IPv6 private
        ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ]

    # Allowed localhost for development
    ALLOWED_LOCALHOST: Final[frozenset[str]] = frozenset(
        {"localhost", "127.0.0.1", "::1"}
    )

    @classmethod
    @lru_cache(maxsize=256)
    def is_blocked_ip(cls, hostname: str) -> bool:
        """Check if hostname resolves to blocked IP range (CACHED).

        :param hostname: Hostname or IP address
        :return: True if blocked
        """
        # Allow localhost in development
        if hostname in cls.ALLOWED_LOCALHOST:
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            return any(ip in blocked for blocked in cls.BLOCKED_IP_RANGES)
        except ValueError:
            # Not an IP address, hostname is OK at this stage
            # DNS resolution happens at connection time
            return False

    @classmethod
    @lru_cache(maxsize=256)
    def _resolve_hostname(cls, hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        """Resolve hostname to IPs (cached).

        :param hostname: Hostname to resolve
        :return: Tuple of resolved IP addresses
        :raises ValueError: If resolution fails
        """
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as e:
            raise ValueError(f"Unable to resolve hostname: {hostname}") from e

        addresses: list[ipaddress._BaseAddress] = []
        for info in infos:
            ip_str = info[4][0]
            try:
                addresses.append(ipaddress.ip_address(ip_str))
            except ValueError:
                continue

        if not addresses:
            raise ValueError(f"Unable to resolve hostname: {hostname}")

        return tuple(addresses)

    @classmethod
    def _resolve_hostname_uncached(
        cls, hostname: str
    ) -> tuple[ipaddress._BaseAddress, ...]:
        """Resolve hostname to IPs (uncached).

        :param hostname: Hostname to resolve
        :return: Tuple of resolved IP addresses
        :raises ValueError: If resolution fails
        """
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as e:
            raise ValueError(f"Unable to resolve hostname: {hostname}") from e

        addresses: list[ipaddress._BaseAddress] = []
        for info in infos:
            ip_str = info[4][0]
            try:
                addresses.append(ipaddress.ip_address(ip_str))
            except ValueError:
                continue

        if not addresses:
            raise ValueError(f"Unable to resolve hostname: {hostname}")

        return tuple(addresses)

    @classmethod
    def is_blocked_hostname(cls, hostname: str) -> bool:
        """Resolve hostname and check if any IP is blocked.

        Blocks if any resolved IP is in a private/reserved range to guard against
        DNS rebinding and mixed public/private records.

        :param hostname: Hostname to resolve and validate
        :return: True if blocked
        :raises ValueError: If resolution fails
        """
        if hostname in cls.ALLOWED_LOCALHOST:
            return False

        for ip in cls._resolve_hostname(hostname):
            if any(ip in blocked for blocked in cls.BLOCKED_IP_RANGES):
                return True
        return False

    @classmethod
    def is_blocked_hostname_uncached(cls, hostname: str) -> bool:
        """Resolve hostname without cache and check if any IP is blocked.

        :param hostname: Hostname to resolve and validate
        :return: True if blocked
        :raises ValueError: If resolution fails
        """
        if hostname in cls.ALLOWED_LOCALHOST:
            return False

        for ip in cls._resolve_hostname_uncached(hostname):
            if any(ip in blocked for blocked in cls.BLOCKED_IP_RANGES):
                return True
        return False


# ===== Credential Sanitization =====


class CredentialSanitizer:
    """Sanitize credentials from strings and exceptions."""

    # Patterns for detecting credentials
    PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
        (
            re.compile(
                r'api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]{20,})',
                re.IGNORECASE,
            ),
            "***API_KEY***",
        ),
        (
            re.compile(r'token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9]{20,})', re.IGNORECASE),
            "***TOKEN***",
        ),
        (
            re.compile(r'password["\']?\s*[:=]\s*["\']?([^\s"\']+)', re.IGNORECASE),
            "***PASSWORD***",
        ),
        (
            re.compile(
                r'cert[_-]?sha256["\']?\s*[:=]\s*["\']?([a-f0-9]{64})', re.IGNORECASE
            ),
            "***CERT***",
        ),
        (
            re.compile(r"bearer\s+([a-zA-Z0-9\-._~+/]+=*)", re.IGNORECASE),
            "Bearer ***TOKEN***",
        ),
        (
            re.compile(r"access_url['\"]?\s*[:=]\s*['\"]?([^\s'\"]+)", re.IGNORECASE),
            "***ACCESS_URL***",
        ),
    ]

    @classmethod
    @lru_cache(maxsize=512)
    def sanitize(cls, text: str) -> str:
        """Remove credentials from string.

        :param text: Text that may contain credentials
        :return: Sanitized text
        """
        if not text:
            return text

        sanitized = text
        for pattern, replacement in cls.PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


# ===== Secure ID Generation =====


class SecureIDGenerator:
    """Cryptographically secure ID generation."""

    __slots__ = ()

    @staticmethod
    def generate_correlation_id() -> str:
        """Generate secure correlation ID with 128 bits entropy.

        Format: {timestamp_us}-{random_hex}

        :return: Correlation ID string
        """
        # 16 bytes = 128 bits of entropy
        random_part = secrets.token_hex(16)

        # Microsecond timestamp for uniqueness and ordering
        timestamp = int(time.time() * 1_000_000)

        return f"{timestamp}-{random_part}"

    @staticmethod
    def generate_request_id() -> str:
        """Generate secure request ID.

        Alias for correlation ID for API compatibility.

        :return: Request ID string
        """
        return SecureIDGenerator.generate_correlation_id()


# ===== Enhanced Sensitive Keys =====

DEFAULT_SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "api_key",
        "apiKey",
        "apikey",
        "token",
        "secret",
        "cert_sha256",
        "certSha256",
        "access_url",
        "accessUrl",
        "authorization",
        "api_url",
        "apiUrl",
    }
)


# ===== Type Guards =====


def is_valid_port(value: object) -> TypeGuard[int]:
    """Type guard for valid port numbers.

    :param value: Value to check
    :return: True if value is valid port
    """
    return isinstance(value, int) and Constants.MIN_PORT <= value <= Constants.MAX_PORT


def is_valid_bytes(value: object) -> TypeGuard[int]:
    """Type guard for valid byte counts.

    :param value: Value to check
    :return: True if value is valid bytes
    """
    return isinstance(value, int) and value >= 0


def is_json_serializable(value: object) -> TypeGuard[JsonValue]:
    """Type guard for JSON-serializable values.

    :param value: Value to check
    :return: True if value is JSON-serializable
    """
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, dict):
        return all(
            isinstance(k, str) and is_json_serializable(v) for k, v in value.items()
        )
    if isinstance(value, list):
        return all(is_json_serializable(item) for item in value)
    return False


# ===== Validators =====


class Validators:
    """Input validation utilities with security hardening."""

    __slots__ = ()

    @staticmethod
    @lru_cache(maxsize=64)
    def validate_cert_fingerprint(fingerprint: SecretStr) -> SecretStr:
        """Validate and normalize certificate fingerprint.

        :param fingerprint: SHA-256 fingerprint
        :return: Normalized fingerprint (lowercase, no separators)
        :raises ValueError: If format is invalid
        """
        if not fingerprint:
            raise ValueError("Certificate fingerprint cannot be empty")

        # Remove common separators
        cleaned = fingerprint.get_secret_value().lower()

        # Validate hex format
        if not re.match(r"^[a-f0-9]{64}$", cleaned):
            raise ValueError(
                f"Invalid certificate fingerprint format. "
                f"Expected 64 hex characters, got: {len(cleaned)}"
            )

        return SecretStr(cleaned)

    @staticmethod
    def validate_port(port: int) -> int:
        """Validate port number.

        :param port: Port number
        :return: Validated port
        :raises ValueError: If port is out of range
        """
        if not is_valid_port(port):
            raise ValueError(
                f"Port must be between {Constants.MIN_PORT} and {Constants.MAX_PORT}"
            )
        return port

    @staticmethod
    def validate_name(name: str) -> str:
        """Validate name field.

        :param name: Name to validate
        :return: Validated name
        :raises ValueError: If name is invalid
        """
        if not name or not name.strip():
            raise ValueError("Name cannot be empty")

        name = name.strip()
        if len(name) > Constants.MAX_NAME_LENGTH:
            raise ValueError(
                f"Name too long: {len(name)} (max {Constants.MAX_NAME_LENGTH})"
            )

        return name

    @staticmethod
    def validate_url(
        url: str,
        *,
        allow_private_networks: bool = True,
        resolve_dns: bool = False,
    ) -> str:
        """Validate and sanitize URL.

        :param url: URL to validate
        :param allow_private_networks: Allow private/local network addresses
        :param resolve_dns: Resolve hostname and block private/reserved IPs
        :return: Validated URL
        :raises ValueError: If URL is invalid
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        url = url.strip()

        if len(url) > Constants.MAX_URL_LENGTH:
            raise ValueError(
                f"URL too long: {len(url)} (max {Constants.MAX_URL_LENGTH})"
            )

        # Check for null bytes
        if "\x00" in url:
            raise ValueError("URL contains null bytes")

        # Parse URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}") from e

        # SSRF protection for raw IPs in hostname (does not resolve DNS)
        if (
            not allow_private_networks
            and parsed.hostname
            and SSRFProtection.is_blocked_ip(parsed.hostname)
        ):
            raise ValueError(
                f"Access to {parsed.hostname} is blocked (SSRF protection)"
            )

        # Explicitly block localhost when private networks are disallowed
        if (
            not allow_private_networks
            and parsed.hostname in SSRFProtection.ALLOWED_LOCALHOST
        ):
            raise ValueError(
                f"Access to {parsed.hostname} is blocked (SSRF protection)"
            )

        # Strict SSRF protection with DNS resolution (guards against rebinding)
        if (
            resolve_dns
            and not allow_private_networks
            and parsed.hostname
            and not SSRFProtection.is_blocked_ip(parsed.hostname)
            and SSRFProtection.is_blocked_hostname(parsed.hostname)
        ):
            raise ValueError(
                f"Access to {parsed.hostname} is blocked (SSRF protection)"
            )

        return url

    @staticmethod
    def validate_string_not_empty(value: str, field_name: str) -> str:
        """Validate string is not empty.

        :param value: String value
        :param field_name: Field name for error messages
        :return: Stripped string
        :raises ValueError: If string is empty
        """
        if not value or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return value.strip()

    @staticmethod
    def _validate_length(value: str, max_length: int, name: str) -> None:
        """Validate string length.

        :param value: String value
        :param max_length: Maximum allowed length
        :param name: Field name for error messages
        :raises ValueError: If string is too long
        """
        if len(value) > max_length:
            raise ValueError(f"{name} too long: {len(value)} (max {max_length})")

    @staticmethod
    def _validate_no_null_bytes(value: str, name: str) -> None:
        """Validate string contains no null bytes.

        :param value: String value
        :param name: Field name for error messages
        :raises ValueError: If string contains null bytes
        """
        if "\x00" in value:
            raise ValueError(f"{name} contains null bytes")

    @staticmethod
    def validate_non_negative(value: DataLimit | int, name: str) -> int:
        """Validate integer is non-negative.

        :param value: Integer value
        :param name: Field name for error messages
        :return: Validated value
        :raises ValueError: If value is negative
        """
        from .models import DataLimit

        raw_value = value.bytes if isinstance(value, DataLimit) else value
        if raw_value < 0:
            raise ValueError(f"{name} must be non-negative, got {raw_value}")
        return raw_value

    @staticmethod
    def validate_since(value: str) -> str:
        """Validate experimental metrics 'since' parameter.

        Accepts:
        - Relative durations: 24h, 7d, 30m, 15s
        - ISO-8601 timestamps (e.g., 2024-01-01T00:00:00Z)

        :param value: Since parameter
        :return: Sanitized since value
        :raises ValueError: If value is invalid
        """
        if not value or not value.strip():
            raise ValueError("'since' parameter cannot be empty")

        sanitized = value.strip()

        # Relative format (number + suffix)
        if len(sanitized) >= 2 and sanitized[-1] in {"h", "d", "m", "s"}:
            number = sanitized[:-1]
            if number.isdigit():
                return sanitized

        # ISO-8601 timestamp (allow trailing Z)
        iso_value = sanitized.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(iso_value)
            return sanitized
        except ValueError:
            raise ValueError(
                "'since' must be a relative duration (e.g., '24h', '7d') "
                "or ISO-8601 timestamp"
            ) from None

    @classmethod
    @lru_cache(maxsize=256)
    def validate_key_id(cls, key_id: str) -> str:
        """Enhanced key_id validation.

        :param key_id: Key ID to validate
        :return: Validated key ID
        :raises ValueError: If key ID is invalid
        """
        clean_id = cls.validate_string_not_empty(key_id, "key_id")
        cls._validate_length(clean_id, Constants.MAX_KEY_ID_LENGTH, "key_id")
        cls._validate_no_null_bytes(clean_id, "key_id")

        try:
            decoded = urllib.parse.unquote(clean_id)
            double_decoded = urllib.parse.unquote(decoded)

            # Check all variants for malicious characters
            for variant in [clean_id, decoded, double_decoded]:
                if any(c in variant for c in {".", "/", "\\", "%", "\x00"}):
                    raise ValueError(
                        "key_id contains invalid characters (., /, \\, %, null)"
                    )
        except Exception as e:
            raise ValueError(f"Invalid key_id encoding: {e}") from e

        # Strict whitelist approach
        allowed_chars = frozenset(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        if not all(c in allowed_chars for c in clean_id):
            raise ValueError("key_id must be alphanumeric, dashes, underscores only")

        return clean_id

    @staticmethod
    @lru_cache(maxsize=256)
    def sanitize_url_for_logging(url: str) -> str:
        """Remove secret path from URL for safe logging.

        :param url: URL to sanitize
        :return: Sanitized URL
        """
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}/***"
        except Exception:
            return "***INVALID_URL***"

    @staticmethod
    @lru_cache(maxsize=512)
    def sanitize_endpoint_for_logging(endpoint: str) -> str:
        """Sanitize endpoint for safe logging.

        :param endpoint: Endpoint to sanitize
        :return: Sanitized endpoint
        """
        if not endpoint:
            return "***EMPTY***"

        parts = endpoint.split("/")
        sanitized = [part if len(part) <= 20 else "***" for part in parts]
        return "/".join(sanitized)


# ===== Base Models =====


class BaseValidatedModel(BaseModel):
    """Base model with strict validation."""

    model_config = ConfigDict(
        validate_assignment=True,
        validate_default=True,
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=False,
        frozen=False,
    )


# ===== Configuration Types =====


class ConfigOverrides(TypedDict, total=False):
    """Type-safe configuration overrides.

    All fields are optional, allowing selective parameter overriding
    while maintaining type safety.
    """

    timeout: int
    retry_attempts: int
    max_connections: int
    rate_limit: int
    user_agent: str
    enable_circuit_breaker: bool
    circuit_failure_threshold: int
    circuit_recovery_timeout: float
    circuit_success_threshold: int
    circuit_call_timeout: float
    enable_logging: bool
    json_format: bool
    allow_private_networks: bool
    resolve_dns_for_ssrf: bool


class ClientDependencies(TypedDict, total=False):
    """Type-safe client dependencies.

    Optional dependencies that can be injected into the client.
    """

    audit_logger: Any  # AuditLogger protocol
    metrics: Any  # MetricsCollector protocol


# ===== Helper Functions =====


def build_config_overrides(
    **kwargs: int | str | bool | float | None,
) -> dict[str, int | str | bool | float | None]:
    """Build configuration overrides dictionary from kwargs.

    DRY implementation - single source of truth for config building.

    :param kwargs: Configuration parameters
    :return: Dictionary containing only non-None values

    Example:
        >>> overrides = build_config_overrides(timeout=20, enable_logging=True)
        >>> # Returns: {'timeout': 20, 'enable_logging': True}
    """
    valid_keys = ConfigOverrides.__annotations__.keys()
    return {k: v for k, v in kwargs.items() if k in valid_keys and v is not None}


def merge_config_kwargs(
    base_kwargs: dict[str, Any],
    overrides: ConfigOverrides,
) -> dict[str, Any]:
    """Merge base kwargs with configuration overrides.

    :param base_kwargs: Base keyword arguments
    :param overrides: Configuration overrides to apply
    :return: Merged dictionary
    """
    return {**base_kwargs, **overrides}


# ===== Masking Utilities =====


def mask_sensitive_data(
    data: Mapping[str, Any],
    *,
    sensitive_keys: frozenset[str] | None = None,
    _depth: int = 0,
) -> dict[str, Any]:
    """Sensitive data masking with lazy copying and optimized recursion.

    Uses lazy copying - only creates new dict when needed.
    Includes recursion depth protection.

    :param data: Data dictionary to mask
    :param sensitive_keys: Set of sensitive key names (case-insensitive matching)
    :param _depth: Current recursion depth (internal)
    :return: Masked data dictionary (may be same object if no sensitive data found)
    """
    # Guard against infinite recursion
    if _depth > Constants.MAX_RECURSION_DEPTH:
        return {"_error": "Max recursion depth exceeded"}

    keys_to_mask = sensitive_keys or DEFAULT_SENSITIVE_KEYS
    keys_lower = {k.lower() for k in keys_to_mask}

    masked: dict[str, Any] | None = None

    for key, value in data.items():
        # Check if key is sensitive
        if key.lower() in keys_lower:
            if masked is None:
                masked = dict(data)
            masked[key] = "***MASKED***"
            continue

        # Recursively handle nested dicts
        if isinstance(value, dict):
            nested = mask_sensitive_data(
                value, sensitive_keys=keys_to_mask, _depth=_depth + 1
            )
            if nested is not value:
                if masked is None:
                    masked = dict(data)
                masked[key] = nested

        # Handle lists containing dicts
        elif isinstance(value, list):
            new_list: list[Any] = []
            list_modified = False

            for item in value:
                if isinstance(item, dict):
                    masked_item = mask_sensitive_data(
                        item, sensitive_keys=keys_to_mask, _depth=_depth + 1
                    )
                    if masked_item is not item:
                        list_modified = True
                    new_list.append(masked_item)
                else:
                    new_list.append(item)

            if list_modified:
                if masked is None:
                    masked = dict(data)
                masked[key] = new_list

    return masked if masked is not None else dict(data)


def validate_snapshot_size(data: dict[str, Any]) -> None:
    """Validate that data size is within limits.

    :param data: Data dictionary to validate
    :raises ValueError: If data exceeds size limit
    """
    size_bytes = sys.getsizeof(data)
    max_bytes = Constants.MAX_SNAPSHOT_SIZE_MB * 1024 * 1024

    if size_bytes > max_bytes:
        raise ValueError(
            f"Data too large: {size_bytes / 1024 / 1024:.2f} MB "
            f"(max {Constants.MAX_SNAPSHOT_SIZE_MB} MB)"
        )


__all__ = [
    "DEFAULT_SENSITIVE_KEYS",
    "AuditDetails",
    "BaseValidatedModel",
    "Bytes",
    "BytesPerUserDict",
    "ChecksDict",
    "ClientDependencies",
    "ConfigOverrides",
    "Constants",
    "CredentialSanitizer",
    "JsonDict",
    "JsonList",
    "JsonPayload",
    "JsonPrimitive",
    "JsonValue",
    "MetricsTags",
    "Port",
    "QueryParams",
    "ResponseData",
    "SSRFProtection",
    "SecureIDGenerator",
    "Timestamp",
    "TimestampMs",
    "TimestampSec",
    "Validators",
    "build_config_overrides",
    "is_json_serializable",
    "is_valid_bytes",
    "is_valid_port",
    "mask_sensitive_data",
    "merge_config_kwargs",
    "validate_snapshot_size",
]
