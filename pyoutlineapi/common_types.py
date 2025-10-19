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

import secrets
import sys
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
    from collections.abc import Mapping

# ===== Type Aliases - Core Types =====

Port: TypeAlias = Annotated[
    int, Field(ge=1025, le=65535, description="Port number (1025-65535)")
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

    MIN_PORT: Final[int] = 1025
    MAX_PORT: Final[int] = 65535

    MAX_NAME_LENGTH: Final[int] = 255
    CERT_FINGERPRINT_LENGTH: Final[int] = 64
    MAX_KEY_ID_LENGTH: Final[int] = 255
    MAX_URL_LENGTH: Final[int] = 2048

    DEFAULT_TIMEOUT: Final[int] = 10
    DEFAULT_RETRY_ATTEMPTS: Final[int] = 2
    DEFAULT_MAX_CONNECTIONS: Final[int] = 10
    DEFAULT_RETRY_DELAY: Final[float] = 1.0
    DEFAULT_USER_AGENT: Final[str] = "PyOutlineAPI/0.4.0"

    MAX_RECURSION_DEPTH: Final[int] = 10
    MAX_SNAPSHOT_SIZE_MB: Final[int] = 10

    RETRY_STATUS_CODES: Final[frozenset[int]] = frozenset(
        {408, 429, 500, 502, 503, 504}
    )


# ===== Enhanced Sensitive Keys =====

DEFAULT_SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "pass",
        "secret",
        "api_key",
        "apikey",
        "api_secret",
        "token",
        "access_token",
        "refresh_token",
        "bearer",
        "auth",
        "authorization",
        "authenticate",
        "session",
        "session_id",
        "sessionid",
        "cookie",
        "cert",
        "certificate",
        "cert_sha256",
        "key",
        "private_key",
        "privatekey",
        "public_key",
        "publickey",
        "access_url",
        "accessurl",
    }
)


# ===== Type Guards =====


def is_valid_port(value: object) -> TypeGuard[Port]:
    """Type-safe port validation.

    :param value: Value to check
    :return: True if value is a valid port
    """
    return isinstance(value, int) and Constants.MIN_PORT <= value <= Constants.MAX_PORT


def is_valid_bytes(value: object) -> TypeGuard[Bytes]:
    """Type-safe bytes validation.

    :param value: Value to check
    :return: True if value is valid bytes count
    """
    return isinstance(value, int) and value >= 0


def is_json_serializable(value: object) -> bool:
    """Check if value is JSON serializable.

    :param value: Value to check
    :return: True if JSON serializable
    """
    return isinstance(value, str | int | float | bool | type(None) | dict | list)


# ===== Security Utilities =====


def secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks.

    :param a: First string
    :param b: Second string
    :return: True if strings match
    """
    try:
        return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except (AttributeError, TypeError):
        return False


# ===== Validators Utility Class =====


class Validators:
    """Enhanced validators with security focus and DRY optimization."""

    __slots__ = ()  # Stateless utility class

    # ===== Helper Methods =====

    @staticmethod
    def _validate_string_not_empty(value: str | None, field_name: str) -> str:
        """Validate that string is not empty after stripping.

        :param value: Value to validate
        :param field_name: Field name for error message
        :return: Stripped string
        :raises ValueError: If string is empty or None
        """
        if value is None or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return value.strip()

    @staticmethod
    def _validate_no_null_bytes(value: str, field_name: str) -> None:
        """Validate that string contains no null bytes.

        :param value: String to validate
        :param field_name: Field name for error message
        :raises ValueError: If null bytes found
        """
        if "\x00" in value:
            raise ValueError(f"{field_name} contains null bytes")

    @staticmethod
    def _validate_length(value: str, max_length: int, field_name: str) -> None:
        """Validate string length.

        :param value: String to validate
        :param max_length: Maximum allowed length
        :param field_name: Field name for error message
        :raises ValueError: If string exceeds max length
        """
        if len(value) > max_length:
            raise ValueError(f"{field_name} too long (max {max_length})")

    # ===== Core Validators =====

    @classmethod
    def validate_port(cls, port: int) -> int:
        """Validate port with type checking.

        Only allows unprivileged ports (1025-65535) for security.

        :param port: Port number to validate
        :return: Validated port number
        :raises ValueError: If port is invalid
        """
        if not isinstance(port, int):
            raise ValueError(f"Port must be int, got {type(port).__name__}")
        if not Constants.MIN_PORT <= port <= Constants.MAX_PORT:
            raise ValueError(f"Port must be {Constants.MIN_PORT}-{Constants.MAX_PORT}")
        return port

    @classmethod
    def validate_url(cls, url: str) -> str:
        """Validate URL with security checks.

        Performs length check, null byte check, and scheme validation.

        :param url: URL to validate
        :return: Validated URL
        :raises ValueError: If URL is invalid
        """
        url = cls._validate_string_not_empty(url, "URL")
        cls._validate_length(url, Constants.MAX_URL_LENGTH, "URL")
        cls._validate_no_null_bytes(url, "URL")

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}") from e

        if not parsed.scheme:
            raise ValueError("URL must include scheme (http/https)")
        if not parsed.netloc:
            raise ValueError("URL must include hostname")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URL scheme must be http or https")

        return url

    @classmethod
    def validate_cert_fingerprint(cls, cert: SecretStr) -> SecretStr:
        """Validate cert fingerprint with enhanced security.

        Checks length, null bytes, and hexadecimal format.

        :param cert: Certificate fingerprint
        :return: Validated fingerprint
        :raises ValueError: If fingerprint is invalid
        """
        parsed_cert = cert.get_secret_value()
        parsed_cert = cls._validate_string_not_empty(parsed_cert, "Certificate")
        parsed_cert = parsed_cert.lower()

        if len(parsed_cert) != Constants.CERT_FINGERPRINT_LENGTH:
            raise ValueError(
                f"Certificate must be {Constants.CERT_FINGERPRINT_LENGTH} hex chars"
            )

        cls._validate_no_null_bytes(parsed_cert, "Certificate")

        if not all(c in "0123456789abcdef" for c in parsed_cert):
            raise ValueError("Certificate must be hexadecimal (0-9, a-f)")

        return cert

    @classmethod
    def validate_name(cls, name: str | None) -> str | None:
        """Validate and normalize name.

        :param name: Name to validate
        :return: Validated name or None if empty
        :raises ValueError: If name exceeds maximum length
        """
        if name is None:
            return None

        if isinstance(name, str):
            name = name.strip()
            if not name:
                return None
            cls._validate_length(name, Constants.MAX_NAME_LENGTH, "Name")
            return name

        return str(name).strip() or None

    @classmethod
    def validate_non_negative(cls, value: int, name: str = "value") -> int:
        """Validate non-negative integer.

        :param value: Value to validate
        :param name: Value name for error message
        :return: Validated value
        :raises ValueError: If value is invalid
        """
        if not isinstance(value, int):
            raise ValueError(f"{name} must be int, got {type(value).__name__}")
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")
        return value

    @classmethod
    def validate_key_id(cls, key_id: str) -> str:
        """Enhanced key_id validation with comprehensive security checks.

        Protects against path traversal, null byte injection, ReDoS, and DoS attacks.

        :param key_id: Key ID to validate
        :return: Validated key ID
        :raises ValueError: If key ID is invalid
        """
        clean_id = cls._validate_string_not_empty(key_id, "key_id")
        cls._validate_length(clean_id, Constants.MAX_KEY_ID_LENGTH, "key_id")
        cls._validate_no_null_bytes(clean_id, "key_id")

        if any(c in clean_id for c in {".", "/", "\\"}):
            raise ValueError("key_id contains invalid characters (., /, \\)")

        allowed_chars = frozenset(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        if not all(c in allowed_chars for c in clean_id):
            raise ValueError("key_id must be alphanumeric, dashes, underscores only")

        return clean_id

    @staticmethod
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
    enable_logging: bool
    json_format: bool


class ClientDependencies(TypedDict, total=False):
    """Type-safe client dependencies.

    Optional dependencies that can be injected into the client.
    """

    audit_logger: Any  # AuditLogger protocol
    metrics: Any  # MetricsCollector protocol


# ===== Helper Functions =====


def build_config_overrides(**kwargs: int | str | bool | None) -> ConfigOverrides:
    """Build configuration overrides dictionary from kwargs.

    DRY implementation - single source of truth for config building.

    :param kwargs: Configuration parameters
    :return: Dictionary containing only non-None values

    Example:
        >>> overrides = build_config_overrides(timeout=20, enable_logging=True)
        >>> # Returns: {'timeout': 20, 'enable_logging': True}
    """
    valid_keys = ConfigOverrides.__annotations__.keys()
    return {k: v for k, v in kwargs.items() if k in valid_keys and v is not None}  # type: ignore[misc]


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
    "JsonDict",
    "JsonList",
    "JsonPayload",
    "JsonPrimitive",
    "JsonValue",
    "MetricsTags",
    "Port",
    "QueryParams",
    "ResponseData",
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
    "secure_compare",
    "validate_snapshot_size",
]
