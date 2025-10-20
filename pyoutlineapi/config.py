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
from typing import TYPE_CHECKING

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .circuit_breaker import CircuitConfig
from .common_types import ConfigOverrides, Validators
from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from typing_extensions import Self

logger = logging.getLogger(__name__)


def _log_if_enabled(level: int, message: str) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    """
    if logger.isEnabledFor(level):
        logger.log(level, message)


def _validate_string_not_empty(value: str | None, field_name: str) -> str:
    """DRY validation for non-empty strings.

    :param value: Value to validate
    :param field_name: Field name for error message
    :return: Stripped string
    :raises ValueError: If string is empty
    """
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value.strip()


class OutlineClientConfig(BaseSettings):
    """Main configuration with enhanced security.

    Provides SecretStr for sensitive data, immutable copies on property access,
    and safe string representation.

    Security features:
    - SecretStr for certificate fingerprint
    - Automatic validation of all fields
    - Safe logging with masked secrets
    - Immutable copies to prevent modification
    - Type-safe field validators
    """

    model_config = SettingsConfigDict(
        env_prefix="OUTLINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
        validate_assignment=True,
        validate_default=True,
        frozen=False,
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
    user_agent: str = Field(
        default="PyOutlineAPI/0.4.0",
        min_length=1,
        max_length=256,
        description="Custom user agent string",
    )

    # ===== Optional Features =====

    enable_circuit_breaker: bool = Field(
        default=True, description="Enable circuit breaker"
    )
    enable_logging: bool = Field(default=False, description="Enable debug logging")
    json_format: bool = Field(default=False, description="Return raw JSON")

    # ===== Circuit Breaker Settings =====

    circuit_failure_threshold: int = Field(
        default=5, ge=1, le=100, description="Failures before opening"
    )
    circuit_recovery_timeout: float = Field(
        default=60.0, ge=1.0, le=3600.0, description="Recovery wait time (seconds)"
    )
    circuit_success_threshold: int = Field(
        default=2, ge=1, le=10, description="Successes needed to close"
    )
    circuit_call_timeout: float = Field(
        default=10.0, ge=0.1, le=300.0, description="Circuit call timeout (seconds)"
    )

    # ===== Validators =====

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """Validate and normalize API URL.

        :param v: URL to validate
        :return: Validated URL
        :raises ValueError: If URL is invalid
        """
        return Validators.validate_url(v)

    @field_validator("cert_sha256")
    @classmethod
    def validate_cert(cls, v: SecretStr) -> SecretStr:
        """Validate certificate fingerprint.

        :param v: Certificate fingerprint
        :return: Validated fingerprint
        :raises ValueError: If fingerprint is invalid
        """
        return Validators.validate_cert_fingerprint(v)

    @field_validator("user_agent")
    @classmethod
    def validate_user_agent(cls, v: str) -> str:
        """Validate user agent string.

        :param v: User agent to validate
        :return: Validated user agent
        :raises ValueError: If user agent is invalid
        """
        v = _validate_string_not_empty(v, "User agent")

        # Check for control characters
        if any(ord(c) < 32 for c in v):
            raise ValueError("User agent contains invalid control characters")

        return v

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        """Additional validation after model creation.

        :return: Validated configuration instance
        """
        # Security warning for HTTP (using helper function)
        if "http://" in self.api_url and "localhost" not in self.api_url:
            _log_if_enabled(
                logging.WARNING,
                "Using HTTP for non-localhost connection. "
                "This is insecure and should only be used for testing.",
            )

        # Circuit breaker timeout adjustment
        if self.enable_circuit_breaker:
            max_request_time = self._calculate_max_request_time()

            if self.circuit_call_timeout < max_request_time:
                _log_if_enabled(
                    logging.WARNING,
                    f"Circuit timeout ({self.circuit_call_timeout}s) is less than "
                    f"max request time ({max_request_time}s). "
                    f"Auto-adjusting to {max_request_time}s.",
                )
                object.__setattr__(self, "circuit_call_timeout", max_request_time)

        return self

    def _calculate_max_request_time(self) -> float:
        """Calculate worst-case request time.

        :return: Maximum request time in seconds
        """
        return self.timeout * (self.retry_attempts + 1) + 10.0

    # ===== Custom __setattr__ for SecretStr Protection =====

    def __setattr__(self, name: str, value: object) -> None:
        """Prevent accidental string assignment to SecretStr fields.

        :param name: Attribute name
        :param value: Attribute value
        :raises TypeError: If trying to assign str to SecretStr field
        """
        if name == "cert_sha256" and isinstance(value, str):
            raise TypeError(
                "cert_sha256 must be SecretStr, not str. Use: SecretStr('your_cert')"
            )
        super().__setattr__(name, value)

    # ===== Helper Methods =====

    def get_cert_sha256(self) -> str:
        """Safely get certificate fingerprint value.

        WARNING: Only use when you actually need the raw value.
        Avoid logging or displaying this value.

        :return: Certificate fingerprint
        """
        return self.cert_sha256.get_secret_value()

    def get_sanitized_config(self) -> dict[str, int | str | bool | float]:
        """Get configuration with sensitive data masked.

        Safe for logging, debugging, and display.

        :return: Sanitized configuration dictionary
        """
        return {
            "api_url": Validators.sanitize_url_for_logging(self.api_url),
            "cert_sha256": "***MASKED***",
            "timeout": self.timeout,
            "retry_attempts": self.retry_attempts,
            "max_connections": self.max_connections,
            "rate_limit": self.rate_limit,
            "user_agent": self.user_agent,
            "enable_circuit_breaker": self.enable_circuit_breaker,
            "enable_logging": self.enable_logging,
            "json_format": self.json_format,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_recovery_timeout": self.circuit_recovery_timeout,
            "circuit_success_threshold": self.circuit_success_threshold,
            "circuit_call_timeout": self.circuit_call_timeout,
        }

    def model_copy_immutable(
        self, **overrides: int | str | bool
    ) -> OutlineClientConfig:
        """Create immutable copy of configuration with optional overrides.

        :param overrides: Configuration parameters to override
        :return: Deep copy of configuration with applied updates

        Example:
            >>> config_copy = config.model_copy_immutable(timeout=20, enable_logging=True)
        """
        valid_overrides = {k: v for k, v in overrides.items() if v is not None}
        return self.model_copy(deep=True, update=valid_overrides)

    def to_dict(self) -> dict[str, int | str | bool | float]:
        """Convert to dictionary (with secrets masked).

        :return: Dictionary representation
        """
        return self.get_sanitized_config()

    def __repr__(self) -> str:
        """Safe string representation without secrets.

        :return: String representation
        """
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
        """User-friendly string representation.

        :return: String representation
        """
        return self.__repr__()

    @property
    def circuit_config(self) -> CircuitConfig | None:
        """Get circuit breaker configuration if enabled.

        :return: Circuit config or None if disabled
        """
        if not self.enable_circuit_breaker:
            return None

        return CircuitConfig(
            failure_threshold=self.circuit_failure_threshold,
            recovery_timeout=self.circuit_recovery_timeout,
            success_threshold=self.circuit_success_threshold,
            call_timeout=self.circuit_call_timeout,
        )

    # ===== Factory Methods =====

    @classmethod
    def from_env(
        cls,
        env_file: Path | str | None = None,
        **overrides: int | str | bool,
    ) -> OutlineClientConfig:
        """Load configuration from environment variables with optional overrides.

        :param env_file: Path to .env file
        :param overrides: Configuration parameters to override
        :return: Configuration instance
        :raises ConfigurationError: If environment configuration is invalid

        Example:
            >>> config = OutlineClientConfig.from_env(
            ...     env_file=".env.prod",
            ...     timeout=20,
            ...     enable_logging=True
            ... )
        """
        # Filter valid overrides using ConfigOverrides type
        valid_keys = ConfigOverrides.__annotations__.keys()
        filtered_overrides = {k: v for k, v in overrides.items() if k in valid_keys}

        if env_file:
            env_path = Path(env_file) if isinstance(env_file, str) else env_file

            # Validate file exists
            if not env_path.exists():
                raise ConfigurationError(
                    f"Environment file not found: {env_path}",
                    field="env_file",
                )

            # Create temporary config class with custom env_file
            class TempConfig(cls):
                model_config = SettingsConfigDict(
                    env_prefix="OUTLINE_",
                    env_file=str(env_path),
                    env_file_encoding="utf-8",
                    case_sensitive=False,
                    extra="forbid",
                )

            return TempConfig(**filtered_overrides)

        return cls(**filtered_overrides)

    @classmethod
    def create_minimal(
        cls,
        api_url: str,
        cert_sha256: str | SecretStr,
        **overrides: int | str | bool,
    ) -> OutlineClientConfig:
        """Create minimal configuration with required parameters only.

        Uses modern **kwargs approach for cleaner API.

        :param api_url: API URL
        :param cert_sha256: Certificate fingerprint
        :param overrides: Optional configuration parameters
        :return: Configuration instance
        :raises TypeError: If cert_sha256 is not str or SecretStr

        Example:
            >>> config = OutlineClientConfig.create_minimal(
            ...     api_url="https://server.com/path",
            ...     cert_sha256="abc123...",
            ...     timeout=20,
            ...     enable_logging=True
            ... )
        """
        if isinstance(cert_sha256, str):
            cert = SecretStr(cert_sha256)
        elif isinstance(cert_sha256, SecretStr):
            cert = cert_sha256
        else:
            raise TypeError(
                f"cert_sha256 must be str or SecretStr, got {type(cert_sha256).__name__}"
            )

        # Filter valid overrides
        valid_keys = ConfigOverrides.__annotations__.keys()
        filtered_overrides = {k: v for k, v in overrides.items() if k in valid_keys}

        return cls(api_url=api_url, cert_sha256=cert, **filtered_overrides)


class DevelopmentConfig(OutlineClientConfig):
    """Development configuration with relaxed security.

    Suitable for local development and testing.
    """

    model_config = SettingsConfigDict(
        env_prefix="DEV_OUTLINE_",
        env_file=".env.dev",
        case_sensitive=False,
        extra="forbid",
    )

    enable_logging: bool = True
    enable_circuit_breaker: bool = False
    timeout: int = 30


class ProductionConfig(OutlineClientConfig):
    """Production configuration with strict security.

    Enforces HTTPS and enables all safety features.
    """

    model_config = SettingsConfigDict(
        env_prefix="PROD_OUTLINE_",
        env_file=".env.prod",
        case_sensitive=False,
        extra="forbid",
    )

    enable_circuit_breaker: bool = True
    enable_logging: bool = False

    @model_validator(mode="after")
    def enforce_security(self) -> Self:
        """Enforce production security requirements.

        :return: Validated configuration
        :raises ConfigurationError: If HTTP is used in production
        """
        # Enforce HTTPS
        if "http://" in self.api_url:
            raise ConfigurationError(
                "Production environment must use HTTPS",
                field="api_url",
                security_issue=True,
            )

        # Warn if circuit breaker is disabled
        if not self.enable_circuit_breaker:
            _log_if_enabled(
                logging.WARNING,
                "Circuit breaker is disabled in production. This is not recommended.",
            )

        return self


# ===== Utility Functions =====


def create_env_template(path: str | Path = ".env.example") -> None:
    """Create .env template file with all options.

    :param path: Path to template file
    """
    template = """# PyOutlineAPI Configuration Template
# Generated by create_env_template()

# ===== Required Settings =====
OUTLINE_API_URL=https://your-server.com:12345/your-secret-path
OUTLINE_CERT_SHA256=your-64-character-sha256-fingerprint

# ===== Client Settings =====
# Timeout for API requests (1-300 seconds)
# OUTLINE_TIMEOUT=10

# Number of retry attempts (0-10)
# OUTLINE_RETRY_ATTEMPTS=2

# Connection pool size (1-100)
# OUTLINE_MAX_CONNECTIONS=10

# Maximum concurrent requests (1-1000)
# OUTLINE_RATE_LIMIT=100

# Custom user agent string
# OUTLINE_USER_AGENT=PyOutlineAPI/0.4.0

# ===== Feature Flags =====
# Enable circuit breaker protection
# OUTLINE_ENABLE_CIRCUIT_BREAKER=true

# Enable debug logging
# OUTLINE_ENABLE_LOGGING=false

# Return raw JSON instead of models
# OUTLINE_JSON_FORMAT=false

# ===== Circuit Breaker Settings =====
# Failures before opening circuit (1-100)
# OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5

# Recovery timeout in seconds (1.0-3600.0)
# OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0

# Successes needed to close circuit (1-10)
# OUTLINE_CIRCUIT_SUCCESS_THRESHOLD=2

# Call timeout in seconds (0.1-300.0)
# OUTLINE_CIRCUIT_CALL_TIMEOUT=10.0
"""

    target_path = Path(path)
    target_path.write_text(template, encoding="utf-8")

    _log_if_enabled(logging.INFO, f"Created configuration template: {target_path}")


def load_config(
    environment: str = "custom",
    **overrides: int | str | bool,
) -> OutlineClientConfig:
    """Load configuration for specific environment with optional overrides.

    Modern approach using **kwargs for cleaner API.

    :param environment: Environment name (development, production, custom)
    :param overrides: Configuration parameters to override
    :return: Configuration instance
    :raises ValueError: If environment name is invalid

    Example:
        >>> config = load_config("production", timeout=20, enable_logging=True)
    """
    config_map: dict[str, type[OutlineClientConfig]] = {
        "development": DevelopmentConfig,
        "dev": DevelopmentConfig,
        "production": ProductionConfig,
        "prod": ProductionConfig,
        "custom": OutlineClientConfig,
    }

    environment_lower = environment.lower()
    config_class = config_map.get(environment_lower)

    if config_class is None:
        valid_envs = ", ".join(sorted(config_map.keys()))
        raise ValueError(f"Invalid environment '{environment}'. Valid: {valid_envs}")

    # Filter valid overrides
    valid_keys = ConfigOverrides.__annotations__.keys()
    filtered_overrides = {k: v for k, v in overrides.items() if k in valid_keys}

    return config_class(**filtered_overrides)


__all__ = [
    "DevelopmentConfig",
    "OutlineClientConfig",
    "ProductionConfig",
    "create_env_template",
    "load_config",
]
