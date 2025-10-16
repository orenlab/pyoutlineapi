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
from typing import Annotated, Any, Final, TypeAlias, TypeGuard
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr

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

# JSON primitive types
JsonPrimitive: TypeAlias = str | int | float | bool | None

# JSON value (recursive type)
JsonValue: TypeAlias = JsonPrimitive | dict[str, Any] | list[Any]

# JSON payload for requests
JsonPayload: TypeAlias = dict[str, JsonValue] | list[JsonValue] | None

# Response data from API
ResponseData: TypeAlias = dict[str, Any]

# Query parameters
QueryParams: TypeAlias = dict[str, str | int | float | bool]

# ===== Type Aliases - Common Structures =====

# Checks dictionary for health monitoring
ChecksDict: TypeAlias = dict[str, dict[str, Any]]

# Bytes per user for metrics
BytesPerUserDict: TypeAlias = dict[str, int]

# Audit details
AuditDetails: TypeAlias = dict[str, str | int | float | bool]

# Metrics tags
MetricsTags: TypeAlias = dict[str, str]


# ===== Constants =====


class Constants:
    """Application-wide constants with security limits."""

    # Port ranges - непривилегированные порты для Outline VPN
    MIN_PORT: Final[int] = 1025
    MAX_PORT: Final[int] = 65535

    # String length limits
    MAX_NAME_LENGTH: Final[int] = 255
    CERT_FINGERPRINT_LENGTH: Final[int] = 64
    MAX_KEY_ID_LENGTH: Final[int] = 255
    MAX_URL_LENGTH: Final[int] = 2048

    # Network and retry settings
    DEFAULT_TIMEOUT: Final[int] = 10
    DEFAULT_RETRY_ATTEMPTS: Final[int] = 2
    DEFAULT_MAX_CONNECTIONS: Final[int] = 10
    DEFAULT_RETRY_DELAY: Final[float] = 1.0
    DEFAULT_USER_AGENT: Final[str] = "PyOutlineAPI/0.4.0"

    # Memory and recursion limits
    MAX_RECURSION_DEPTH: Final[int] = 10
    MAX_SNAPSHOT_SIZE_MB: Final[int] = 10

    # HTTP status codes for retry
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


# ===== Type Guards (Python 3.10+) =====


def is_valid_port(value: Any) -> TypeGuard[Port]:
    """Type-safe port validation."""
    return isinstance(value, int) and Constants.MIN_PORT <= value <= Constants.MAX_PORT


def is_valid_bytes(value: Any) -> TypeGuard[Bytes]:
    """Type-safe bytes validation."""
    return isinstance(value, int) and value >= 0


def is_json_serializable(value: Any) -> bool:
    """Check if value is JSON serializable."""
    return isinstance(value, (str, int, float, bool, type(None), dict, list))


# ===== Security Utilities =====


def secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    try:
        return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except Exception:
        return False


# ===== Validators =====


class Validators:
    """Enhanced validators with security focus."""

    @staticmethod
    def validate_port(port: int) -> int:
        """Validate port with type checking.

        Only allows unprivileged ports (1025-65535) for security.
        """
        if not isinstance(port, int):
            raise ValueError(f"Port must be int, got {type(port).__name__}")
        if not Constants.MIN_PORT <= port <= Constants.MAX_PORT:
            raise ValueError(f"Port must be {Constants.MIN_PORT}-{Constants.MAX_PORT}")
        return port

    @staticmethod
    def validate_url(url: str) -> str:
        """Validate URL with security checks."""
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        url = url.strip()

        # Length check (DoS protection)
        if len(url) > Constants.MAX_URL_LENGTH:
            raise ValueError(f"URL too long (max {Constants.MAX_URL_LENGTH})")

        # Null byte check
        if "\x00" in url:
            raise ValueError("URL contains null bytes")

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}") from e

        if not parsed.scheme:
            raise ValueError("URL must include scheme (http/https)")
        if not parsed.netloc:
            raise ValueError("URL must include hostname")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL scheme must be http or https")

        return url

    @staticmethod
    def validate_cert_fingerprint(cert: SecretStr) -> SecretStr:
        """Validate cert fingerprint with enhanced security."""
        parsed_cert = cert.get_secret_value()
        if not parsed_cert or not parsed_cert.strip():
            raise ValueError("Certificate fingerprint cannot be empty")

        parsed_cert = parsed_cert.strip().lower()

        # Length check BEFORE other checks (ReDoS protection)
        if len(parsed_cert) != Constants.CERT_FINGERPRINT_LENGTH:
            raise ValueError(
                f"Certificate must be {Constants.CERT_FINGERPRINT_LENGTH} hex chars"
            )

        # Null byte check
        if "\x00" in parsed_cert:
            raise ValueError("Certificate contains null bytes")

        # Fast character validation (no regex needed)
        if not all(c in "0123456789abcdef" for c in parsed_cert):
            raise ValueError("Certificate must be hexadecimal (0-9, a-f)")

        return cert

    @staticmethod
    def validate_name(name: str | None) -> str | None:
        """Validate and normalize name."""
        if name is None:
            return None

        if isinstance(name, str):
            name = name.strip()
            if not name:
                return None
            if len(name) > Constants.MAX_NAME_LENGTH:
                raise ValueError(f"Name max {Constants.MAX_NAME_LENGTH} chars")
            return name

        return str(name).strip() or None

    @staticmethod
    def validate_non_negative(value: int, name: str = "value") -> int:
        """Validate non-negative integer."""
        if not isinstance(value, int):
            raise ValueError(f"{name} must be int, got {type(value).__name__}")
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")
        return value

    @staticmethod
    def validate_key_id(key_id: str) -> str:
        """Enhanced key_id validation with comprehensive security checks.

        Protects against:
        - Path traversal attacks
        - Null byte injection
        - ReDoS attacks
        - DoS via length
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        clean_id = key_id.strip()

        # Length check FIRST (DoS protection)
        if len(clean_id) > Constants.MAX_KEY_ID_LENGTH:
            raise ValueError(f"key_id too long (max {Constants.MAX_KEY_ID_LENGTH})")

        # Null byte check (injection protection)
        if "\x00" in clean_id:
            raise ValueError("key_id contains null bytes")

        # Path traversal protection
        if any(c in clean_id for c in (".", "/", "\\")):
            raise ValueError("key_id contains invalid characters (., /, \\)")

        # Simple character validation (no regex = no ReDoS)
        allowed_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        if not all(c in allowed_chars for c in clean_id):
            raise ValueError("key_id must be alphanumeric, dashes, underscores only")

        return clean_id

    @staticmethod
    def sanitize_url_for_logging(url: str) -> str:
        """Remove secret path from URL for safe logging."""
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}/***"
        except Exception:
            return "***INVALID_URL***"

    @staticmethod
    def sanitize_endpoint_for_logging(endpoint: str) -> str:
        """Sanitize endpoint for safe logging."""
        if not endpoint:
            return "***EMPTY***"

        parts = endpoint.split("/")
        sanitized = []
        for part in parts:
            # Mask long parts (likely secrets)
            if len(part) > 20:
                sanitized.append("***")
            else:
                sanitized.append(part)

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
    )


# ===== Optimized Utility Functions =====


def mask_sensitive_data(
    data: dict[str, Any],
    *,
    sensitive_keys: frozenset[str] | None = None,
    _depth: int = 0,
) -> dict[str, Any]:
    """Optimized sensitive data masking with lazy copying.

    Features:
    - Lazy copying (only when needed)
    - Recursion depth protection
    - Case-insensitive key matching
    """
    if _depth > Constants.MAX_RECURSION_DEPTH:
        return {"_error": "Max recursion depth exceeded"}

    keys_to_mask = sensitive_keys or DEFAULT_SENSITIVE_KEYS
    keys_lower = {k.lower() for k in keys_to_mask}

    # Lazy copy - only create new dict if we need to modify
    masked = data
    needs_copy = False

    for key, value in data.items():
        # Check if this key should be masked
        if key.lower() in keys_lower:
            if not needs_copy:
                masked = data.copy()
                needs_copy = True
            masked[key] = "***MASKED***"

        # Recursively handle nested structures
        elif isinstance(value, dict):
            nested = mask_sensitive_data(
                value, sensitive_keys=keys_to_mask, _depth=_depth + 1
            )
            if nested is not value:  # Changed
                if not needs_copy:
                    masked = data.copy()
                    needs_copy = True
                masked[key] = nested

        elif isinstance(value, list):
            new_list = []
            list_changed = False
            for item in value:
                if isinstance(item, dict):
                    masked_item = mask_sensitive_data(
                        item, sensitive_keys=keys_to_mask, _depth=_depth + 1
                    )
                    if masked_item is not item:
                        list_changed = True
                    new_list.append(masked_item)
                else:
                    new_list.append(item)

            if list_changed:
                if not needs_copy:
                    masked = data.copy()
                    needs_copy = True
                masked[key] = new_list

    return masked


def validate_snapshot_size(data: dict[str, Any]) -> None:
    """Validate that data size is within limits."""
    size_bytes = sys.getsizeof(data)
    max_bytes = Constants.MAX_SNAPSHOT_SIZE_MB * 1024 * 1024

    if size_bytes > max_bytes:
        raise ValueError(
            f"Data too large: {size_bytes / 1024 / 1024:.2f} MB "
            f"(max {Constants.MAX_SNAPSHOT_SIZE_MB} MB)"
        )


__all__ = [
    # Core type aliases
    "Port",
    "Bytes",
    "Timestamp",
    "TimestampMs",
    "TimestampSec",
    # JSON type aliases
    "JsonPrimitive",
    "JsonValue",
    "JsonPayload",
    "ResponseData",
    "QueryParams",
    # Common structures
    "ChecksDict",
    "BytesPerUserDict",
    "AuditDetails",
    "MetricsTags",
    # Constants
    "Constants",
    "DEFAULT_SENSITIVE_KEYS",
    # Type guards
    "is_valid_port",
    "is_valid_bytes",
    "is_json_serializable",
    # Security
    "secure_compare",
    # Validators
    "Validators",
    # Base model
    "BaseValidatedModel",
    # Utilities
    "mask_sensitive_data",
    "validate_snapshot_size",
]
