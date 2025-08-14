"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

from __future__ import annotations

import re
from typing import Annotated, Any, final
from urllib.parse import urlparse

from pydantic import Field, field_validator, BaseModel

# Common type definitions using Python 3.10+ Annotated
Port = Annotated[
    int,
    Field(
        gt=1024,
        lt=65536,
        description="Port number (1025-65535)",
        json_schema_extra={"example": 8388},
    ),
]

ServerId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        description="Server identifier",
        json_schema_extra={"example": "server-123"},
    ),
]

AccessKeyId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        description="Access key identifier",
        json_schema_extra={"example": "key-456"},
    ),
]

Bytes = Annotated[
    int,
    Field(
        ge=0,
        description="Size in bytes",
        json_schema_extra={"example": 1073741824},  # 1GB
    ),
]

Timestamp = Annotated[
    int,
    Field(
        ge=0, description="Unix timestamp", json_schema_extra={"example": 1640995200}
    ),
]

CertFingerprint = Annotated[
    str,
    Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA-256 certificate fingerprint (64 hex characters)",
        json_schema_extra={"example": "a1b2c3d4e5f6..."},
    ),
]


class CommonValidators:
    """Common validation functions used across models."""

    @staticmethod
    def validate_port(port: int) -> int:
        """Validate port number is in allowed range."""
        if not 1025 <= port <= 65535:
            raise ValueError(
                f"Port must be in range 1025-65535 (privileged ports not allowed), got {port}"
            )
        return port

    @staticmethod
    def validate_url(url: str) -> str:
        """Validate URL format and components."""
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
    def validate_cert_fingerprint(cert: str) -> str:
        """Validate certificate SHA-256 fingerprint format."""
        if not cert or not cert.strip():
            raise ValueError("Certificate fingerprint cannot be empty")

        cert = cert.strip().lower()

        if len(cert) != 64:
            raise ValueError("Certificate fingerprint must be exactly 64 characters")

        if not re.match(r"^[a-f0-9]{64}$", cert):
            raise ValueError(
                "Certificate fingerprint must contain only hexadecimal characters"
            )

        return cert

    @staticmethod
    def normalize_asn(value: Any) -> int | None:
        """Normalize ASN value (convert 0 to None)."""
        if value == 0 or value == "":
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return int(value) if value is not None else None

    @staticmethod
    def normalize_empty_string(value: Any) -> str | None:
        """Normalize empty strings to None."""
        if value == "" or value == 0:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return str(value) if value is not None else None

    @staticmethod
    def validate_non_negative_bytes(value: int) -> int:
        """Validate bytes value is non-negative."""
        if value < 0:
            raise ValueError("Bytes value must be non-negative")
        return value

    @staticmethod
    def validate_name(name: str) -> str:
        """Validate name is not empty and reasonable length."""
        if not name or not name.strip():
            raise ValueError("Name cannot be empty")
        name = name.strip()
        if len(name) > 255:
            raise ValueError("Name cannot exceed 255 characters")
        return name

    @staticmethod
    def validate_optional_name(name: str | None) -> str | None:
        """Validate optional name, allowing empty strings to be converted to None."""
        if name is None:
            return None
        if isinstance(name, str):
            name = name.strip()
            # Convert empty strings to None (API sometimes returns empty strings)
            if not name:
                return None
            if len(name) > 255:
                raise ValueError("Name cannot exceed 255 characters")
            return name
        return str(name).strip() or None


class BaseValidatedModel(BaseModel):
    """Base model with common validation and configuration."""

    class Config:
        # Use enum values instead of enum objects in serialization
        use_enum_values = True
        # Validate field assignment
        validate_assignment = True
        # Allow population by field name or alias
        populate_by_name = True
        # Strict mode for better type safety
        str_strip_whitespace = True
        # Generate JSON schema
        json_schema_mode = "validation"


class TimestampMixin(BaseModel):
    """Mixin for models that include timestamps."""

    created_at: Timestamp | None = Field(
        None, description="Creation timestamp", alias="createdAt"
    )

    updated_at: Timestamp | None = Field(
        None, description="Last update timestamp", alias="updatedAt"
    )


class NamedEntityMixin(BaseModel):
    """Mixin for models that have names."""

    name: str = Field(description="Entity name", min_length=1, max_length=255)

    @classmethod
    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        """Validate name using common validator."""
        return CommonValidators.validate_name(v)


# Constants
@final
class Constants:
    """Application constants."""

    # Port ranges
    MIN_PORT = 1025
    MAX_PORT = 65535

    # Size limits
    MAX_NAME_LENGTH = 255
    MAX_SERVER_ID_LENGTH = 64
    MAX_ACCESS_KEY_ID_LENGTH = 64

    # Certificate
    CERT_FINGERPRINT_LENGTH = 64

    # Default values
    DEFAULT_TIMEOUT = 30
    DEFAULT_RETRY_ATTEMPTS = 3
    DEFAULT_MAX_CONNECTIONS = 10
    DEFAULT_RETRY_DELAY = 1.0

    # User agent
    DEFAULT_USER_AGENT = "PyOutlineAPI/0.4.0"


# Utility functions
def mask_sensitive_data(
    data: dict[str, Any], sensitive_keys: set[str] | None = None
) -> dict[str, Any]:
    """Mask sensitive data in dictionaries for logging."""
    if sensitive_keys is None:
        sensitive_keys = {"password", "cert_sha256", "access_url", "accessUrl", "token"}

    masked = {}
    for key, value in data.items():
        if key.lower() in {k.lower() for k in sensitive_keys}:
            masked[key] = "***MASKED***"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_data(value, sensitive_keys)
        elif isinstance(value, list):
            masked[key] = [
                mask_sensitive_data(item, sensitive_keys)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            masked[key] = value

    return masked
