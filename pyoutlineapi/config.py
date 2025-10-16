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

import logging
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .circuit_breaker import CircuitConfig
from .common_types import Validators
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class OutlineClientConfig(BaseSettings):
    """Main configuration with enhanced security.

    SECURITY FEATURES:
    - SecretStr for sensitive data
    - Immutable copies on property access
    - Safe __repr__ without secrets
    - Type enforcement
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

    api_url: str = Field(..., description="Outline server API URL with secret path")
    cert_sha256: SecretStr = Field(..., description="SHA-256 certificate fingerprint")

    # ===== Client Settings =====

    timeout: int = Field(
        default=10, ge=1, le=300, description="Request timeout (seconds)"
    )
    retry_attempts: int = Field(default=2, ge=0, le=10, description="Number of retries")
    max_connections: int = Field(
        default=10, ge=1, le=100, description="Connection pool size"
    )
    rate_limit: int = Field(
        default=100, ge=1, le=1000, description="Max concurrent requests"
    )

    # ===== Optional Features =====

    enable_circuit_breaker: bool = Field(
        default=True, description="Enable circuit breaker"
    )
    enable_logging: bool = Field(default=False, description="Enable debug logging")
    json_format: bool = Field(default=False, description="Return raw JSON")

    # ===== Circuit Breaker Settings =====

    circuit_failure_threshold: int = Field(
        default=5, ge=1, description="Failures before opening"
    )
    circuit_recovery_timeout: float = Field(
        default=60.0, ge=1.0, description="Recovery wait time"
    )
    circuit_call_timeout: float = Field(
        default=10.0, ge=1.0, description="Circuit call timeout"
    )

    # ===== Validators =====

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """Validate and normalize API URL."""
        return Validators.validate_url(v)

    @field_validator("cert_sha256")
    @classmethod
    def validate_cert(cls, v: SecretStr) -> SecretStr:
        """Validate certificate fingerprint."""
        return Validators.validate_cert_fingerprint(v)

    @model_validator(mode="after")
    def validate_config(self) -> OutlineClientConfig:
        """Additional validation after model creation."""
        # Security warning for HTTP
        if "http://" in self.api_url and "localhost" not in self.api_url:
            logger.warning(
                "Using HTTP for non-localhost connection. "
                "This is insecure and should only be used for testing."
            )

        # Validate circuit timeout makes sense
        if self.enable_circuit_breaker:
            max_request_time = self.timeout * (self.retry_attempts + 1) + 10
            if self.circuit_call_timeout < max_request_time:
                logger.warning(
                    f"Circuit timeout ({self.circuit_call_timeout}s) is less than "
                    f"max request time ({max_request_time}s). Adjusting."
                )
                self.circuit_call_timeout = max_request_time

        return self

    # ===== Custom __setattr__ for SecretStr Protection =====

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent accidental string assignment to SecretStr fields."""
        if name == "cert_sha256" and isinstance(value, str):
            raise TypeError(
                "cert_sha256 must be SecretStr, not str. " "Use: SecretStr('your_cert')"
            )
        super().__setattr__(name, value)

    # ===== Helper Methods =====

    def get_cert_sha256(self) -> str:
        """Safely get certificate fingerprint value.

        WARNING: Only use when you actually need the raw value.
        Prefer keeping it as SecretStr.
        """
        return self.cert_sha256.get_secret_value()

    def get_sanitized_config(self) -> dict[str, Any]:
        """Get configuration with sensitive data masked.

        Safe for logging, debugging, and display.
        """
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
            "circuit_call_timeout": self.circuit_call_timeout,
        }

    def model_copy_immutable(self, **updates: Any) -> OutlineClientConfig:
        """Create immutable copy of configuration.

        Returns a deep copy that can be safely returned to users.
        """
        return self.model_copy(deep=True, update=updates)

    def __repr__(self) -> str:
        """Safe string representation without secrets."""
        safe_url = Validators.sanitize_url_for_logging(self.api_url)
        cb_status = "enabled" if self.enable_circuit_breaker else "disabled"
        return (
            f"OutlineClientConfig("
            f"url={safe_url}, "
            f"cert='***', "
            f"timeout={self.timeout}s, "
            f"circuit_breaker={cb_status})"
        )

    def __str__(self) -> str:
        """Safe string representation."""
        return self.__repr__()

    @property
    def circuit_config(self) -> CircuitConfig | None:
        """Get circuit breaker configuration if enabled."""
        if not self.enable_circuit_breaker:
            return None

        return CircuitConfig(
            failure_threshold=self.circuit_failure_threshold,
            recovery_timeout=self.circuit_recovery_timeout,
            call_timeout=self.circuit_call_timeout,
        )

    # ===== Factory Methods =====

    @classmethod
    def from_env(
        cls,
        env_file: Path | str | None = None,
        **overrides: Any,
    ) -> OutlineClientConfig:
        """Load configuration from environment variables."""
        if env_file:

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
        """Create minimal configuration with required parameters only."""
        if isinstance(cert_sha256, str):
            cert_sha256 = SecretStr(cert_sha256)

        return cls(api_url=api_url, cert_sha256=cert_sha256, **kwargs)


class DevelopmentConfig(OutlineClientConfig):
    """Development configuration with relaxed security."""

    model_config = SettingsConfigDict(
        env_prefix="DEV_OUTLINE_",
        env_file=".env.dev",
    )

    enable_logging: bool = True
    enable_circuit_breaker: bool = False


class ProductionConfig(OutlineClientConfig):
    """Production configuration with strict security."""

    model_config = SettingsConfigDict(
        env_prefix="PROD_OUTLINE_",
        env_file=".env.prod",
    )

    @model_validator(mode="after")
    def enforce_security(self) -> ProductionConfig:
        """Enforce production security requirements."""
        if "http://" in self.api_url:
            raise ConfigurationError(
                "Production environment must use HTTPS",
                field="api_url",
                security_issue=True,
            )
        return self


# ===== Utility Functions =====


def create_env_template(path: str | Path = ".env.example") -> None:
    """Create .env template file with all options."""
    template = """# PyOutlineAPI Configuration
# Required settings
OUTLINE_API_URL=https://your-server.com:12345/your-secret-path
OUTLINE_CERT_SHA256=your-64-character-sha256-fingerprint

# Optional client settings
# OUTLINE_TIMEOUT=10
# OUTLINE_RETRY_ATTEMPTS=2
# OUTLINE_MAX_CONNECTIONS=10
# OUTLINE_RATE_LIMIT=100

# Optional features
# OUTLINE_ENABLE_CIRCUIT_BREAKER=true
# OUTLINE_ENABLE_LOGGING=false
# OUTLINE_JSON_FORMAT=false

# Circuit breaker settings
# OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5
# OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0
# OUTLINE_CIRCUIT_CALL_TIMEOUT=10.0
"""

    Path(path).write_text(template, encoding="utf-8")
    logger.info(f"Created configuration template: {path}")


def load_config(environment: str = "custom", **overrides: Any) -> OutlineClientConfig:
    """Load configuration for specific environment."""
    config_map = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "custom": OutlineClientConfig,
    }

    config_class = config_map.get(environment, OutlineClientConfig)
    return config_class(**overrides)


__all__ = [
    "DevelopmentConfig",
    "OutlineClientConfig",
    "ProductionConfig",
    "create_env_template",
    "load_config",
]
