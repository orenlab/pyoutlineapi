"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Common types, validators, and constants.

Provides type aliases, validation functions, and application-wide constants
with security-first design.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Final
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr

# ===== Type Aliases =====

Port = Annotated[
    int,
    Field(gt=1024, lt=65536, description="Port number (1025-65535)"),
]

Bytes = Annotated[
    int,
    Field(ge=0, description="Size in bytes"),
]

Timestamp = Annotated[
    int,
    Field(ge=0, description="Unix timestamp in milliseconds"),
]


# ===== Constants =====


class Constants:
    """
    Application-wide constants.

    Centralized configuration values used throughout the library.
    """

    # Port ranges
    MIN_PORT: Final = 1025
    MAX_PORT: Final = 65535

    # Size limits
    MAX_NAME_LENGTH: Final = 255
    CERT_FINGERPRINT_LENGTH: Final = 64

    # Default values
    DEFAULT_TIMEOUT: Final = 30
    DEFAULT_RETRY_ATTEMPTS: Final = 3
    DEFAULT_MAX_CONNECTIONS: Final = 10
    DEFAULT_RETRY_DELAY: Final = 1.0
    DEFAULT_USER_AGENT: Final = "PyOutlineAPI/0.4.0"


# ===== Validators =====


class Validators:
    """
    Common validation functions with security focus.

    All validators are designed with security in mind:
    - No sensitive data in exceptions
    - Input sanitization
    - Path traversal protection
    - Injection attack prevention
    """

    @staticmethod
    def validate_port(port: int) -> int:
        """
        Validate port is in allowed range.

        Args:
            port: Port number to validate

        Returns:
            int: Validated port number

        Raises:
            ValueError: If port is out of valid range

        Example:
            >>> Validators.validate_port(8388)
            8388
            >>> Validators.validate_port(80)  # Raises ValueError
        """
        if not Constants.MIN_PORT <= port <= Constants.MAX_PORT:
            raise ValueError(
                f"Port must be {Constants.MIN_PORT}-{Constants.MAX_PORT}, got {port}"
            )
        return port

    @staticmethod
    def validate_url(url: str) -> str:
        """
        Validate URL format and structure.

        Args:
            url: URL string to validate

        Returns:
            str: Validated and normalized URL

        Raises:
            ValueError: If URL format is invalid

        Example:
            >>> Validators.validate_url("https://server.com:12345/path")
            'https://server.com:12345/path'
            >>> Validators.validate_url("invalid")  # Raises ValueError
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        url = url.strip()
        parsed = urlparse(url)

        if not parsed.scheme:
            raise ValueError("URL must include scheme (http/https)")
        if not parsed.netloc:
            raise ValueError("URL must include hostname")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL scheme must be http or https")

        return url

    @staticmethod
    def validate_cert_fingerprint(cert: SecretStr) -> SecretStr:
        """
        Validate SHA-256 certificate fingerprint.

        Security: Certificate value is kept in SecretStr and never exposed
        in exception messages.

        Args:
            cert: Certificate fingerprint as SecretStr

        Returns:
            SecretStr: Validated certificate fingerprint (still as SecretStr)

        Raises:
            ValueError: If certificate format is invalid (without exposing value)

        Example:
            >>> from pydantic import SecretStr
            >>> cert = SecretStr("a" * 64)  # 64 hex chars
            >>> Validators.validate_cert_fingerprint(cert)
            SecretStr('**********')
        """
        parsed_cert = cert.get_secret_value()
        if not parsed_cert or not parsed_cert.strip():
            raise ValueError("Certificate fingerprint cannot be empty")

        parsed_cert = parsed_cert.strip().lower()

        if len(parsed_cert) != Constants.CERT_FINGERPRINT_LENGTH:
            # 🔒 SECURITY: Don't expose actual length or value
            raise ValueError(
                f"Certificate fingerprint must be exactly "
                f"{Constants.CERT_FINGERPRINT_LENGTH} hexadecimal characters"
            )

        if not re.match(r"^[a-f0-9]{64}$", parsed_cert):
            # 🔒 SECURITY: Don't expose actual value
            raise ValueError(
                "Certificate fingerprint must contain only "
                "hexadecimal characters (0-9, a-f)"
            )

        return cert

    @staticmethod
    def validate_name(name: str | None) -> str | None:
        """
        Validate and normalize name string.

        Args:
            name: Name string to validate (can be None)

        Returns:
            str | None: Validated name or None if empty

        Raises:
            ValueError: If name is too long

        Example:
            >>> Validators.validate_name("Alice")
            'Alice'
            >>> Validators.validate_name("  Bob  ")
            'Bob'
            >>> Validators.validate_name("")  # Returns None
        """
        if name is None:
            return None

        if isinstance(name, str):
            name = name.strip()
            if not name:  # Empty after strip
                return None
            if len(name) > Constants.MAX_NAME_LENGTH:
                raise ValueError(
                    f"Name cannot exceed {Constants.MAX_NAME_LENGTH} characters"
                )
            return name

        return str(name).strip() or None

    @staticmethod
    def validate_non_negative(value: int, name: str = "value") -> int:
        """
        Validate value is non-negative.

        Args:
            value: Value to validate
            name: Field name for error message

        Returns:
            int: Validated value

        Raises:
            ValueError: If value is negative

        Example:
            >>> Validators.validate_non_negative(100, "bytes_limit")
            100
            >>> Validators.validate_non_negative(-1, "bytes_limit")
            # Raises: ValueError: bytes_limit must be non-negative, got -1
        """
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")
        return value

    @staticmethod
    def validate_key_id(key_id: str) -> str:
        """
        Validate key_id to prevent injection attacks.

        Security features:
        - Prevents path traversal (../)
        - Allows only safe characters
        - Enforces length limits
        - Protects against DoS with length check

        Args:
            key_id: Access key identifier to validate

        Returns:
            str: Validated and sanitized key_id

        Raises:
            ValueError: If key_id is invalid or contains unsafe characters

        Example:
            >>> Validators.validate_key_id("user-001")
            'user-001'
            >>> Validators.validate_key_id("../etc/passwd")
            # Raises: ValueError: key_id contains invalid characters
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        clean_id = key_id.strip()

        # Maximum length check (prevent DoS)
        if len(clean_id) > 255:
            raise ValueError("key_id too long (maximum 255 characters)")

        # 🔒 SECURITY: Prevent path traversal
        if ".." in clean_id or "/" in clean_id or "\\" in clean_id:
            raise ValueError(
                "key_id contains invalid characters (path traversal detected)"
            )

        # 🔒 SECURITY: Allow only safe alphanumeric characters
        if not re.match(r"^[a-zA-Z0-9_-]+$", clean_id):
            raise ValueError(
                "key_id must contain only alphanumeric characters, "
                "dashes, and underscores"
            )

        return clean_id

    @staticmethod
    def sanitize_url_for_logging(url: str) -> str:
        """
        Remove secret path from URL for safe logging.

        Security: Prevents secret path leakage in logs and error tracking.

        Args:
            url: Full URL with potential secret path

        Returns:
            str: Sanitized URL with only scheme://netloc/***

        Example:
            >>> Validators.sanitize_url_for_logging("https://server.com:12345/secret123")
            'https://server.com:12345/***'
            >>> Validators.sanitize_url_for_logging("invalid url")
            '***INVALID_URL***'
        """
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}/***"
        except Exception:
            return "***INVALID_URL***"


# ===== Base Models =====


class BaseValidatedModel(BaseModel):
    """
    Base model with common configuration.

    Provides strict validation and flexible field handling
    for all Pydantic models in the library.
    """

    model_config = ConfigDict(
        # Strict validation
        validate_assignment=True,
        validate_default=True,
        # Flexibility
        populate_by_name=True,
        use_enum_values=True,
        # Cleanliness
        str_strip_whitespace=True,
        # Performance
        arbitrary_types_allowed=False,
    )


# ===== Utility Functions =====


def mask_sensitive_data(
    data: dict[str, Any],
    *,
    sensitive_keys: set[str] | None = None,
) -> dict[str, Any]:
    """
    Mask sensitive data for logging.

    Security: Prevents accidental leakage of credentials, tokens, and URLs
    in logs, error tracking, and debugging output.

    Args:
        data: Dictionary to mask
        sensitive_keys: Keys to mask (default: common sensitive fields)

    Returns:
        dict: Dictionary with masked values

    Example:
        >>> data = {"password": "secret123", "name": "user1"}
        >>> mask_sensitive_data(data)
        {'password': '***MASKED***', 'name': 'user1'}
        >>>
        >>> # With custom sensitive keys
        >>> mask_sensitive_data(data, sensitive_keys={"name"})
        {'password': 'secret123', 'name': '***MASKED***'}
    """
    if sensitive_keys is None:
        sensitive_keys = {
            "password",
            "cert_sha256",
            "access_url",
            "accessUrl",
            "token",
            "secret",
            "key",
            "api_key",
            "apiKey",
            "certificate",
        }

    masked = {}
    for key, value in data.items():
        if key.lower() in {k.lower() for k in sensitive_keys}:
            masked[key] = "***MASKED***"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_data(value, sensitive_keys=sensitive_keys)
        elif isinstance(value, list):
            masked[key] = [
                mask_sensitive_data(item, sensitive_keys=sensitive_keys)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            masked[key] = value

    return masked


__all__ = [
    # Types
    "Port",
    "Bytes",
    "Timestamp",
    # Constants
    "Constants",
    # Validators
    "Validators",
    # Base models
    "BaseValidatedModel",
    # Utilities
    "mask_sensitive_data",
]
