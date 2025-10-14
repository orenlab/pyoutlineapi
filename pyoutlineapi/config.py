"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Configuration with pydantic-settings and SecretStr.

Provides flexible configuration loading from environment variables,
.env files, or direct parameters with security-first design.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .circuit_breaker import CircuitConfig
from .common_types import Validators
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


# ===== Configuration Models =====


class OutlineClientConfig(BaseSettings):
    """
    Main configuration with environment variable support.

    Security features:
    - SecretStr for sensitive data (cert_sha256)
    - Input validation for all fields
    - Safe defaults
    - HTTP warning for non-localhost connections

    Configuration sources (in priority order):
    1. Direct parameters
    2. Environment variables (with OUTLINE_ prefix)
    3. .env file
    4. Default values

    Example:
        >>> # From environment variables
        >>> config = OutlineClientConfig()
        >>>
        >>> # With direct parameters
        >>> from pydantic import SecretStr
        >>> config = OutlineClientConfig(
        ...     api_url="https://server.com:12345/secret",
        ...     cert_sha256=SecretStr("abc123..."),
        ...     timeout=60,
        ... )
    """

    model_config = SettingsConfigDict(
        env_prefix="OUTLINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
        validate_assignment=True,
        validate_default=True,
    )

    # ===== Core Settings (Required) =====

    api_url: str = Field(
        ...,
        description="Outline server API URL with secret path",
    )

    cert_sha256: SecretStr = Field(
        ...,
        description="SHA-256 certificate fingerprint (protected with SecretStr)",
    )

    # ===== Client Settings =====

    timeout: int = Field(
        default=10,  # Reduced from 30s - more reasonable for VPN API
        ge=1,
        le=300,
        description="Request timeout in seconds (default: 10s)",
    )

    retry_attempts: int = Field(
        default=2,  # Reduced from 3 - total 3 attempts (1 initial + 2 retries)
        ge=0,
        le=10,
        description="Number of retry attempts (default: 2, total attempts: 3)",
    )

    max_connections: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum connection pool size",
    )

    rate_limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum concurrent requests",
    )

    # ===== Optional Features =====

    enable_circuit_breaker: bool = Field(
        default=True,
        description="Enable circuit breaker protection",
    )

    enable_logging: bool = Field(
        default=False,
        description="Enable debug logging (WARNING: may log sanitized URLs)",
    )

    json_format: bool = Field(
        default=False,
        description="Return raw JSON instead of Pydantic models",
    )

    # ===== Circuit Breaker Settings =====

    circuit_failure_threshold: int = Field(
        default=5,
        ge=1,
        description="Failures before opening circuit",
    )

    circuit_recovery_timeout: float = Field(
        default=60.0,
        ge=1.0,
        description="Seconds before testing recovery",
    )

    # ===== Validators =====

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """
        Validate and normalize API URL.

        Raises:
            ValueError: If URL format is invalid
        """
        return Validators.validate_url(v)

    @field_validator("cert_sha256")
    @classmethod
    def validate_cert(cls, v: SecretStr) -> SecretStr:
        """
        Validate certificate fingerprint.

        Security: Certificate value stays in SecretStr and is never
        exposed in validation error messages.

        Raises:
            ValueError: If certificate format is invalid
        """
        return Validators.validate_cert_fingerprint(v)

    @model_validator(mode="after")
    def validate_config(self) -> OutlineClientConfig:
        """
        Additional validation after model creation.

        Security warnings:
        - HTTP for non-localhost connections
        """
        # Warn about insecure settings
        if "http://" in self.api_url and "localhost" not in self.api_url:
            logger.warning(
                "Using HTTP for non-localhost connection. "
                "This is insecure and should only be used for testing."
            )

        return self

    # ===== Helper Methods =====

    def get_cert_sha256(self) -> str:
        """
        Safely get certificate fingerprint value.

        Security: Only use this when you actually need the certificate value.
        Prefer keeping it as SecretStr whenever possible.

        Returns:
            str: Certificate fingerprint as string

        Example:
            >>> config = OutlineClientConfig.from_env()
            >>> cert_value = config.get_cert_sha256()
            >>> # Use cert_value for SSL validation
        """
        return self.cert_sha256.get_secret_value()

    def get_sanitized_config(self) -> dict[str, Any]:
        """
        Get configuration with sensitive data masked.

        Safe for logging, debugging, and display purposes.

        Returns:
            dict: Configuration with masked sensitive values

        Example:
            >>> config = OutlineClientConfig.from_env()
            >>> safe_config = config.get_sanitized_config()
            >>> logger.info(f"Config: {safe_config}")  # ✅ Safe
            >>> print(safe_config)
            {
                'api_url': 'https://server.com:12345/***',
                'cert_sha256': '***MASKED***',
                'timeout': 10,
                ...
            }
        """
        from .common_types import Validators

        return {
            "api_url": Validators.sanitize_url_for_logging(self.api_url),
            "cert_sha256": "***MASKED***",
            "timeout": self.timeout,
            "retry_attempts": self.retry_attempts,
            "max_connections": self.max_connections,
            "rate_limit": self.rate_limit,
            "enable_circuit_breaker": self.enable_circuit_breaker,
            "enable_logging": self.enable_logging,
            "json_format": self.json_format,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_recovery_timeout": self.circuit_recovery_timeout,
        }

    def __repr__(self) -> str:
        """
        Safe string representation without exposing secrets.

        Returns:
            str: String representation with masked sensitive data
        """
        from .common_types import Validators

        safe_url = Validators.sanitize_url_for_logging(self.api_url)
        return (
            f"OutlineClientConfig("
            f"url={safe_url}, "
            f"timeout={self.timeout}s, "
            f"circuit_breaker={'enabled' if self.enable_circuit_breaker else 'disabled'}"
            f")"
        )

    def __str__(self) -> str:
        """Safe string representation."""
        return self.__repr__()

    @property
    def circuit_config(self) -> CircuitConfig | None:
        """
        Get circuit breaker configuration if enabled.

        Returns:
            CircuitConfig | None: Circuit config if enabled, None otherwise

        Example:
            >>> config = OutlineClientConfig.from_env()
            >>> if config.circuit_config:
            ...     print(f"Circuit breaker enabled")
            ...     print(f"Failure threshold: {config.circuit_config.failure_threshold}")
        """
        if not self.enable_circuit_breaker:
            return None

        return CircuitConfig(
            failure_threshold=self.circuit_failure_threshold,
            recovery_timeout=self.circuit_recovery_timeout,
            call_timeout=self.timeout,  # Will be adjusted by base_client if needed
        )

    # ===== Factory Methods =====

    @classmethod
    def from_env(
        cls,
        env_file: Path | str | None = None,
        **overrides: Any,
    ) -> OutlineClientConfig:
        """
        Load configuration from environment variables.

        Environment variables should be prefixed with OUTLINE_:
        - OUTLINE_API_URL
        - OUTLINE_CERT_SHA256
        - OUTLINE_TIMEOUT
        - etc.

        Args:
            env_file: Path to .env file (default: .env)
            **overrides: Override specific values

        Returns:
            OutlineClientConfig: Configured instance

        Example:
            >>> # From default .env file
            >>> config = OutlineClientConfig.from_env()
            >>>
            >>> # From custom file
            >>> config = OutlineClientConfig.from_env(".env.production")
            >>>
            >>> # With overrides
            >>> config = OutlineClientConfig.from_env(timeout=60)
        """
        if env_file:
            # Create temp class with custom env file
            class TempConfig(cls):
                model_config = SettingsConfigDict(
                    env_prefix="OUTLINE_",
                    env_file=str(env_file),
                    env_file_encoding="utf-8",
                    case_sensitive=False,
                    extra="forbid",
                )

            return TempConfig(**overrides)

        return cls(**overrides)

    @classmethod
    def create_minimal(
        cls,
        api_url: str,
        cert_sha256: str | SecretStr,
        **kwargs: Any,
    ) -> OutlineClientConfig:
        """
        Create minimal configuration with required parameters only.

        Args:
            api_url: API URL with secret path
            cert_sha256: Certificate fingerprint (string or SecretStr)
            **kwargs: Additional optional settings

        Returns:
            OutlineClientConfig: Configured instance

        Example:
            >>> config = OutlineClientConfig.create_minimal(
            ...     api_url="https://server.com:12345/secret",
            ...     cert_sha256="abc123...",
            ... )
            >>>
            >>> # With additional settings
            >>> config = OutlineClientConfig.create_minimal(
            ...     api_url="https://server.com:12345/secret",
            ...     cert_sha256="abc123...",
            ...     timeout=60,
            ...     enable_circuit_breaker=False,
            ... )
        """
        # Convert cert to SecretStr if needed
        if isinstance(cert_sha256, str):
            cert_sha256 = SecretStr(cert_sha256)

        return cls(
            api_url=api_url,
            cert_sha256=cert_sha256,
            **kwargs,
        )


# ===== Environment-specific Configs =====


class DevelopmentConfig(OutlineClientConfig):
    """
    Development configuration with relaxed security.

    Use for local development and testing only.

    Features:
    - Logging enabled by default
    - Circuit breaker disabled for easier debugging
    - Uses DEV_OUTLINE_ prefix for environment variables

    Example:
        >>> config = DevelopmentConfig()
        >>> # Or from custom env file
        >>> config = DevelopmentConfig.from_env(".env.dev")
    """

    model_config = SettingsConfigDict(
        env_prefix="DEV_OUTLINE_",
        env_file=".env.dev",
    )

    enable_logging: bool = True
    enable_circuit_breaker: bool = False  # Easier debugging


class ProductionConfig(OutlineClientConfig):
    """
    Production configuration with strict security.

    Enforces:
    - HTTPS only (no HTTP allowed)
    - Circuit breaker enabled by default
    - Uses PROD_OUTLINE_ prefix for environment variables

    Example:
        >>> config = ProductionConfig()
        >>> # Or from custom env file
        >>> config = ProductionConfig.from_env(".env.prod")
    """

    model_config = SettingsConfigDict(
        env_prefix="PROD_OUTLINE_",
        env_file=".env.prod",
    )

    @model_validator(mode="after")
    def enforce_security(self) -> ProductionConfig:
        """
        Enforce production security requirements.

        Raises:
            ConfigurationError: If security requirements are not met
        """
        if "http://" in self.api_url:
            raise ConfigurationError(
                "Production environment must use HTTPS",
                field="api_url",
                security_issue=True,
            )

        return self


# ===== Utility Functions =====


def create_env_template(path: str | Path = ".env.example") -> None:
    """
    Create .env template file with all available options.

    Creates a well-documented template file that users can copy
    and customize for their environment.

    Args:
        path: Path where to create template file (default: .env.example)

    Example:
        >>> from pyoutlineapi import create_env_template
        >>> create_env_template()
        >>> # Edit .env.example with your values
        >>> # Copy to .env for production use
        >>>
        >>> # Or create custom location
        >>> create_env_template("config/.env.template")
    """
    template = """# PyOutlineAPI Configuration
# Required settings
OUTLINE_API_URL=https://your-server.com:12345/your-secret-path
OUTLINE_CERT_SHA256=your-64-character-sha256-fingerprint

# Optional client settings (optimized defaults)
# OUTLINE_TIMEOUT=10          # Request timeout in seconds (default: 10s)
# OUTLINE_RETRY_ATTEMPTS=2    # Retry attempts, total 3 attempts (default: 2)
# OUTLINE_MAX_CONNECTIONS=10  # Connection pool size (default: 10)
# OUTLINE_RATE_LIMIT=100      # Max concurrent requests (default: 100)

# Optional features
# OUTLINE_ENABLE_CIRCUIT_BREAKER=true  # Circuit breaker protection (default: true)
# OUTLINE_ENABLE_LOGGING=false         # Debug logging (default: false)
# OUTLINE_JSON_FORMAT=false            # Return JSON dicts instead of models (default: false)

# Circuit breaker settings (if enabled)
# OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5     # Failures before opening (default: 5)
# OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0   # Recovery wait time in seconds (default: 60.0)

# Notes:
# - Total request time: ~(TIMEOUT * (RETRY_ATTEMPTS + 1) + delays)
# - With defaults: ~38s max (10s * 3 attempts + 3s delays + buffer)
# - For slower connections, increase TIMEOUT and/or RETRY_ATTEMPTS
"""

    Path(path).write_text(template, encoding="utf-8")
    logger.info(f"Created configuration template: {path}")


def load_config(
    environment: Literal["development", "production", "custom"] = "custom",
    **overrides: Any,
) -> OutlineClientConfig:
    """
    Load configuration for specific environment.

    Args:
        environment: Environment type (development, production, or custom)
        **overrides: Override specific values

    Returns:
        OutlineClientConfig: Configured instance for the specified environment

    Example:
        >>> # Production config
        >>> config = load_config("production")
        >>>
        >>> # Development config with overrides
        >>> config = load_config("development", timeout=120)
        >>>
        >>> # Custom config
        >>> config = load_config("custom", enable_logging=True)
    """
    config_map = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "custom": OutlineClientConfig,
    }

    config_class = config_map[environment]
    return config_class(**overrides)


__all__ = [
    "OutlineClientConfig",
    "DevelopmentConfig",
    "ProductionConfig",
    "create_env_template",
    "load_config",
]
