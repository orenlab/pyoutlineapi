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

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING, LiteralString
from urllib.parse import urlparse

# Import CircuitConfig for runtime use
from .circuit_breaker import CircuitConfig
from .common_types import CommonValidators, Constants
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutlineClientConfig:
    """
    Immutable configuration for AsyncOutlineClient.

    This configuration class provides comprehensive validation and supports
    loading from environment variables with proper error handling.
    """

    # Core connection settings
    api_url: str
    cert_sha256: str | None | LiteralString

    # Client behavior settings
    json_format: bool = False
    timeout: int = Constants.DEFAULT_TIMEOUT
    retry_attempts: int = Constants.DEFAULT_RETRY_ATTEMPTS
    enable_logging: bool = False
    user_agent: str | None = None
    max_connections: int = Constants.DEFAULT_MAX_CONNECTIONS
    rate_limit_delay: float = 0.0

    # Circuit breaker settings
    circuit_breaker_enabled: bool = True
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 60.0
    circuit_success_threshold: int = 3
    circuit_failure_rate_threshold: float = 0.5
    circuit_min_calls_to_evaluate: int = 10

    # Health monitoring settings
    enable_health_monitoring: bool = True
    enable_metrics_collection: bool = True

    def __post_init__(self) -> None:
        """Validate configuration after creation."""
        self._validate_core_settings()
        self._validate_client_settings()
        self._validate_circuit_breaker_settings()

    def _validate_core_settings(self) -> None:
        """Validate core connection settings."""
        try:
            # Validate and normalize URL
            validated_url = CommonValidators.validate_url(self.api_url)
            object.__setattr__(self, "api_url", validated_url.rstrip("/"))

            # Validate certificate fingerprint
            validated_cert = CommonValidators.validate_cert_fingerprint(
                self.cert_sha256
            )
            object.__setattr__(self, "cert_sha256", validated_cert)

        except ValueError as e:
            raise ConfigurationError(f"Invalid core settings: {e}")

    def _validate_client_settings(self) -> None:
        """Validate client behavior settings."""
        if self.timeout <= 0:
            raise ConfigurationError(
                "timeout must be positive", "timeout", self.timeout
            )

        if self.timeout > 300:  # 5 minutes max
            raise ConfigurationError(
                "timeout should not exceed 300 seconds", "timeout", self.timeout
            )

        if self.retry_attempts < 0:
            raise ConfigurationError(
                "retry_attempts cannot be negative",
                "retry_attempts",
                self.retry_attempts,
            )

        if self.retry_attempts > 10:
            raise ConfigurationError(
                "retry_attempts should not exceed 10",
                "retry_attempts",
                self.retry_attempts,
            )

        if self.max_connections <= 0:
            raise ConfigurationError(
                "max_connections must be positive",
                "max_connections",
                self.max_connections,
            )

        if self.rate_limit_delay < 0:
            raise ConfigurationError(
                "rate_limit_delay cannot be negative",
                "rate_limit_delay",
                self.rate_limit_delay,
            )

    def _validate_circuit_breaker_settings(self) -> None:
        """Validate circuit breaker settings."""
        if not self.circuit_breaker_enabled:
            return

        if self.circuit_failure_threshold <= 0:
            raise ConfigurationError(
                "circuit_failure_threshold must be positive",
                "circuit_failure_threshold",
                self.circuit_failure_threshold,
            )

        if self.circuit_recovery_timeout <= 0:
            raise ConfigurationError(
                "circuit_recovery_timeout must be positive",
                "circuit_recovery_timeout",
                self.circuit_recovery_timeout,
            )

        if self.circuit_success_threshold <= 0:
            raise ConfigurationError(
                "circuit_success_threshold must be positive",
                "circuit_success_threshold",
                self.circuit_success_threshold,
            )

        if not 0 < self.circuit_failure_rate_threshold <= 1:
            raise ConfigurationError(
                "circuit_failure_rate_threshold must be between 0 and 1",
                "circuit_failure_rate_threshold",
                self.circuit_failure_rate_threshold,
            )

        if self.circuit_min_calls_to_evaluate <= 0:
            raise ConfigurationError(
                "circuit_min_calls_to_evaluate must be positive",
                "circuit_min_calls_to_evaluate",
                self.circuit_min_calls_to_evaluate,
            )

    @classmethod
    def from_env(
        cls,
        prefix: str = "OUTLINE_",
        required: bool = True,
        env_file: Optional[Path | str] = None,
        validate_connection: bool = False,
    ) -> OutlineClientConfig:
        """
        Create configuration from environment variables.

        Environment Variables:
            Core Settings (Required):
                OUTLINE_API_URL: Outline server API URL
                OUTLINE_CERT_SHA256: Server certificate SHA-256 fingerprint

            Client Settings (Optional):
                OUTLINE_JSON_FORMAT: Return raw JSON instead of models (default: false)
                OUTLINE_TIMEOUT: Request timeout in seconds (default: 30)
                OUTLINE_RETRY_ATTEMPTS: Number of retry attempts (default: 3)
                OUTLINE_ENABLE_LOGGING: Enable debug logging (default: false)
                OUTLINE_USER_AGENT: Custom user agent string
                OUTLINE_MAX_CONNECTIONS: Connection pool size (default: 10)
                OUTLINE_RATE_LIMIT_DELAY: Delay between requests in seconds (default: 0.0)

            Circuit Breaker Settings (Optional):
                OUTLINE_CIRCUIT_BREAKER_ENABLED: Enable circuit breaker (default: true)
                OUTLINE_CIRCUIT_FAILURE_THRESHOLD: Failures before opening (default: 5)
                OUTLINE_CIRCUIT_RECOVERY_TIMEOUT: Recovery timeout in seconds (default: 60.0)
                OUTLINE_CIRCUIT_SUCCESS_THRESHOLD: Successes to close circuit (default: 3)
                OUTLINE_CIRCUIT_FAILURE_RATE_THRESHOLD: Failure rate threshold (default: 0.5)
                OUTLINE_CIRCUIT_MIN_CALLS: Min calls before evaluation (default: 10)

            Health Monitoring Settings (Optional):
                OUTLINE_ENABLE_HEALTH_MONITORING: Enable health monitoring (default: true)
                OUTLINE_ENABLE_METRICS_COLLECTION: Enable metrics collection (default: true)

        Args:
            prefix: Environment variable prefix (default: "OUTLINE_")
            required: Require mandatory variables or use safe defaults for testing
            env_file: Path to .env file to load variables from
            validate_connection: Validate that URL is reachable (for production use)

        Returns:
            Validated OutlineClientConfig instance

        Raises:
            ConfigurationError: If validation fails or required variables are missing

        Examples:
            Basic usage::

                config = OutlineClientConfig.from_env()
                client = AsyncOutlineClient.from_config(config)

            Custom prefix for multiple environments::

                prod_config = OutlineClientConfig.from_env(prefix="PROD_OUTLINE_")
                dev_config = OutlineClientConfig.from_env(prefix="DEV_OUTLINE_")

            Load from .env file::

                config = OutlineClientConfig.from_env(env_file=".env.production")

            For testing with safe defaults::

                config = OutlineClientConfig.from_env(required=False)
        """
        # Load environment file if specified
        if env_file:
            cls._load_env_file(Path(env_file))

        # Get core settings
        api_url = os.getenv(f"{prefix}API_URL")
        cert_sha256 = os.getenv(f"{prefix}CERT_SHA256")

        # Validate required settings
        if required:
            if not api_url:
                raise ConfigurationError(
                    f"Environment variable {prefix}API_URL is required. "
                    f"Set it to your Outline server API URL (e.g., https://server.com:12345/secret)"
                )
            if not cert_sha256:
                raise ConfigurationError(
                    f"Environment variable {prefix}CERT_SHA256 is required. "
                    f"Set it to your server's certificate SHA-256 fingerprint"
                )
        else:
            # Use safe defaults for testing
            api_url = api_url or "https://outline.example.com:12345/test"
            cert_sha256 = cert_sha256 or "a" * 64

        try:
            # Parse client settings
            json_format = cls._parse_bool(os.getenv(f"{prefix}JSON_FORMAT", "false"))
            timeout = cls._parse_int(
                os.getenv(f"{prefix}TIMEOUT", str(Constants.DEFAULT_TIMEOUT)),
                min_val=1,
                max_val=300,
            )
            retry_attempts = cls._parse_int(
                os.getenv(
                    f"{prefix}RETRY_ATTEMPTS", str(Constants.DEFAULT_RETRY_ATTEMPTS)
                ),
                min_val=0,
                max_val=10,
            )
            enable_logging = cls._parse_bool(
                os.getenv(f"{prefix}ENABLE_LOGGING", "false")
            )
            user_agent = os.getenv(f"{prefix}USER_AGENT") or None
            max_connections = cls._parse_int(
                os.getenv(
                    f"{prefix}MAX_CONNECTIONS", str(Constants.DEFAULT_MAX_CONNECTIONS)
                ),
                min_val=1,
            )
            rate_limit_delay = cls._parse_float(
                os.getenv(f"{prefix}RATE_LIMIT_DELAY", "0.0"), min_val=0.0
            )

            # Parse circuit breaker settings
            circuit_breaker_enabled = cls._parse_bool(
                os.getenv(f"{prefix}CIRCUIT_BREAKER_ENABLED", "true")
            )
            circuit_failure_threshold = cls._parse_int(
                os.getenv(f"{prefix}CIRCUIT_FAILURE_THRESHOLD", "5"), min_val=1
            )
            circuit_recovery_timeout = cls._parse_float(
                os.getenv(f"{prefix}CIRCUIT_RECOVERY_TIMEOUT", "60.0"), min_val=1.0
            )
            circuit_success_threshold = cls._parse_int(
                os.getenv(f"{prefix}CIRCUIT_SUCCESS_THRESHOLD", "3"), min_val=1
            )
            circuit_failure_rate_threshold = cls._parse_float(
                os.getenv(f"{prefix}CIRCUIT_FAILURE_RATE_THRESHOLD", "0.5"),
                min_val=0.01,
                max_val=1.0,
            )
            circuit_min_calls_to_evaluate = cls._parse_int(
                os.getenv(f"{prefix}CIRCUIT_MIN_CALLS", "10"), min_val=1
            )

            # Parse health monitoring settings
            enable_health_monitoring = cls._parse_bool(
                os.getenv(f"{prefix}ENABLE_HEALTH_MONITORING", "true")
            )
            enable_metrics_collection = cls._parse_bool(
                os.getenv(f"{prefix}ENABLE_METRICS_COLLECTION", "true")
            )

            # Optional connection validation
            if validate_connection and required:
                cls._validate_connection(api_url, cert_sha256)

            # Create configuration
            config = cls(
                api_url=api_url,
                cert_sha256=cert_sha256,
                json_format=json_format,
                timeout=timeout,
                retry_attempts=retry_attempts,
                enable_logging=enable_logging,
                user_agent=user_agent,
                max_connections=max_connections,
                rate_limit_delay=rate_limit_delay,
                circuit_breaker_enabled=circuit_breaker_enabled,
                circuit_failure_threshold=circuit_failure_threshold,
                circuit_recovery_timeout=circuit_recovery_timeout,
                circuit_success_threshold=circuit_success_threshold,
                circuit_failure_rate_threshold=circuit_failure_rate_threshold,
                circuit_min_calls_to_evaluate=circuit_min_calls_to_evaluate,
                enable_health_monitoring=enable_health_monitoring,
                enable_metrics_collection=enable_metrics_collection,
            )

            if enable_logging:
                logger.info(
                    f"Configuration loaded successfully from environment (prefix: {prefix})"
                )

            return config

        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            raise ConfigurationError(
                f"Failed to load configuration from environment: {e}"
            ) from e

    @staticmethod
    def _parse_bool(value: str) -> bool:
        """Parse boolean value from string."""
        if isinstance(value, bool):
            return value
        return value.lower() in ("true", "1", "yes", "on", "enabled")

    @staticmethod
    def _parse_int(
        value: str, min_val: int | None = None, max_val: int | None = None
    ) -> int:
        """Parse integer with validation."""
        try:
            result = int(value)
        except (ValueError, TypeError) as e:
            raise ConfigurationError(f"Cannot convert '{value}' to integer") from e

        if min_val is not None and result < min_val:
            raise ConfigurationError(f"Value {result} is below minimum {min_val}")
        if max_val is not None and result > max_val:
            raise ConfigurationError(f"Value {result} is above maximum {max_val}")

        return result

    @staticmethod
    def _parse_float(
        value: str, min_val: float | None = None, max_val: float | None = None
    ) -> float:
        """Parse float with validation."""
        try:
            result = float(value)
        except (ValueError, TypeError) as e:
            raise ConfigurationError(f"Cannot convert '{value}' to float") from e

        if min_val is not None and result < min_val:
            raise ConfigurationError(f"Value {result} is below minimum {min_val}")
        if max_val is not None and result > max_val:
            raise ConfigurationError(f"Value {result} is above maximum {max_val}")

        return result

    @staticmethod
    def _load_env_file(file_path: Path) -> None:
        """Load variables from .env file."""
        if not file_path.exists():
            raise ConfigurationError(f"Environment file not found: {file_path}")

        try:
            with file_path.open(encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Skip comments and empty lines
                    if not line or line.startswith("#"):
                        continue

                    # Parse KEY=VALUE
                    if "=" not in line:
                        logger.warning(
                            f"Skipping invalid line {line_num} in {file_path}: {line}"
                        )
                        continue

                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Remove quotes
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]

                    # Set environment variable only if not already set
                    if key not in os.environ:
                        os.environ[key] = value

        except Exception as e:
            raise ConfigurationError(
                f"Failed to read environment file {file_path}: {e}"
            ) from e

    @staticmethod
    def _validate_connection(api_url: str, cert_sha256: str) -> None:
        """Validate that the connection settings are reachable (optional)."""
        try:
            parsed = urlparse(api_url)
            if not parsed.netloc:
                raise ConfigurationError("Invalid API URL format")

            # TODO: Add actual connection test if needed
            # This could involve a simple HTTP request to validate connectivity

        except Exception as e:
            raise ConfigurationError(f"Connection validation failed: {e}") from e

    def get_circuit_config(self) -> CircuitConfig | None:
        """Get CircuitConfig object from settings."""
        if not self.circuit_breaker_enabled:
            return None

        return CircuitConfig(
            failure_threshold=self.circuit_failure_threshold,
            recovery_timeout=self.circuit_recovery_timeout,
            success_threshold=self.circuit_success_threshold,
            call_timeout=self.timeout,
            failure_rate_threshold=self.circuit_failure_rate_threshold,
            min_calls_to_evaluate=self.circuit_min_calls_to_evaluate,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary (without sensitive data)."""
        return {
            "api_url": self.api_url,
            "cert_sha256": "***masked***",  # Mask sensitive data
            "json_format": self.json_format,
            "timeout": self.timeout,
            "retry_attempts": self.retry_attempts,
            "enable_logging": self.enable_logging,
            "user_agent": self.user_agent,
            "max_connections": self.max_connections,
            "rate_limit_delay": self.rate_limit_delay,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_recovery_timeout": self.circuit_recovery_timeout,
            "circuit_success_threshold": self.circuit_success_threshold,
            "circuit_failure_rate_threshold": self.circuit_failure_rate_threshold,
            "circuit_min_calls_to_evaluate": self.circuit_min_calls_to_evaluate,
            "enable_health_monitoring": self.enable_health_monitoring,
            "enable_metrics_collection": self.enable_metrics_collection,
        }

    def __repr__(self) -> str:
        """String representation without sensitive data."""
        parsed = urlparse(self.api_url)
        safe_url = (
            f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else "***masked***"
        )

        return (
            f"OutlineClientConfig("
            f"url={safe_url}, "
            f"timeout={self.timeout}s, "
            f"circuit_breaker={self.circuit_breaker_enabled}, "
            f"logging={self.enable_logging})"
        )


def create_env_template(file_path: Path | str = ".env.example") -> None:
    """
    Create a comprehensive .env template file for Outline API configuration.

    Args:
        file_path: Path where to create the template file

    Examples:
        Create default template::

            create_env_template()  # Creates .env.example

        Create custom template::

            create_env_template(".env.production")  # Custom path
    """

    template = """# PyOutlineAPI Configuration Template
# Copy this file to .env and fill in your values

# ============================================================================
# CORE SETTINGS (Required)
# ============================================================================

# Your Outline server API URL (get this from your server setup)
# Example: https://123.45.67.89:12345/secretpath
OUTLINE_API_URL=https://your-server.com:port/secret-path

# Server certificate SHA-256 fingerprint (get this from your server setup)
# Example: a1b2c3d4e5f6789...
OUTLINE_CERT_SHA256=your-64-character-cert-fingerprint


# ============================================================================
# CLIENT BEHAVIOR SETTINGS (Optional)
# ============================================================================

# Return raw JSON instead of Pydantic models (default: false)
OUTLINE_JSON_FORMAT=false

# Request timeout in seconds (default: 30)
OUTLINE_TIMEOUT=30

# Number of retry attempts for failed requests (default: 3)
OUTLINE_RETRY_ATTEMPTS=3

# Enable debug logging (default: false)
OUTLINE_ENABLE_LOGGING=false

# Custom User-Agent string (optional)
# OUTLINE_USER_AGENT=MyApp/1.0

# Maximum number of HTTP connections in pool (default: 10)
OUTLINE_MAX_CONNECTIONS=10

# Minimum delay between requests in seconds (default: 0.0)
OUTLINE_RATE_LIMIT_DELAY=0.0


# ============================================================================
# CIRCUIT BREAKER SETTINGS (Optional)
# ============================================================================

# Enable circuit breaker protection (default: true)
OUTLINE_CIRCUIT_BREAKER_ENABLED=true

# Number of failures before opening circuit (default: 5)
OUTLINE_CIRCUIT_FAILURE_THRESHOLD=5

# Time to wait before trying to close circuit in seconds (default: 60.0)
OUTLINE_CIRCUIT_RECOVERY_TIMEOUT=60.0

# Number of successes needed to close circuit (default: 3)
OUTLINE_CIRCUIT_SUCCESS_THRESHOLD=3

# Failure rate threshold to open circuit (0.0-1.0, default: 0.5)
OUTLINE_CIRCUIT_FAILURE_RATE_THRESHOLD=0.5

# Minimum calls before evaluating failure rate (default: 10)
OUTLINE_CIRCUIT_MIN_CALLS=10


# ============================================================================
# HEALTH MONITORING SETTINGS (Optional)
# ============================================================================

# Enable health monitoring features (default: true)
OUTLINE_ENABLE_HEALTH_MONITORING=true

# Enable performance metrics collection (default: true)
OUTLINE_ENABLE_METRICS_COLLECTION=true


# ============================================================================
# ENVIRONMENT-SPECIFIC EXAMPLES
# ============================================================================

# Development Environment:
# OUTLINE_API_URL=http://localhost:3000/secret
# OUTLINE_ENABLE_LOGGING=true
# OUTLINE_CIRCUIT_BREAKER_ENABLED=false

# Production Environment:
# OUTLINE_API_URL=https://outline.company.com:443/api/secret
# OUTLINE_TIMEOUT=60
# OUTLINE_RETRY_ATTEMPTS=5
# OUTLINE_CIRCUIT_FAILURE_THRESHOLD=3
# OUTLINE_ENABLE_METRICS_COLLECTION=true

# Testing Environment:
# OUTLINE_API_URL=https://test-outline.company.com/secret
# OUTLINE_JSON_FORMAT=true
# OUTLINE_ENABLE_LOGGING=true
"""

    file_path = Path(file_path)
    file_path.write_text(template.strip(), encoding="utf-8")
    print(f"✓ Created environment template: {file_path}")
    print(f"  Copy it to .env and configure your settings")


# Integration with existing AsyncOutlineClient
def _add_from_env_method() -> None:
    """Add from_env class method to AsyncOutlineClient."""
    try:
        from .client import AsyncOutlineClient
    except ImportError:
        # Client not available yet
        return

    @classmethod
    def from_env(
        cls,
        prefix: str = "OUTLINE_",
        required: bool = True,
        env_file: Optional[Path | str] = None,
        validate_connection: bool = False,
        **kwargs: Any,
    ) -> AsyncOutlineClient:
        """
        Create AsyncOutlineClient from environment variables.

        This factory method loads configuration from environment variables
        and creates a properly configured client instance.

        Args:
            prefix: Environment variable prefix (default: "OUTLINE_")
            required: Require mandatory variables or use safe defaults
            env_file: Path to .env file to load variables from
            validate_connection: Validate connection settings
            **kwargs: Additional client options (override env settings)

        Returns:
            Configured AsyncOutlineClient instance

        Raises:
            ConfigurationError: If configuration is invalid

        Examples:
            Basic usage::

                async with AsyncOutlineClient.from_env() as client:
                    server = await client.get_server_info()

            Custom environment prefix::

                client = AsyncOutlineClient.from_env(prefix="PROD_OUTLINE_")

            Load from custom .env file::

                client = AsyncOutlineClient.from_env(env_file=".env.production")

            Override specific settings::

                client = AsyncOutlineClient.from_env(
                    enable_logging=True,  # Override env setting
                    timeout=60            # Override env setting
                )
        """
        # Load configuration from environment
        config = OutlineClientConfig.from_env(
            prefix=prefix,
            required=required,
            env_file=env_file,
            validate_connection=validate_connection,
        )

        # Prepare client arguments from config
        client_kwargs = {
            "api_url": config.api_url,
            "cert_sha256": config.cert_sha256,
            "json_format": config.json_format,
            "timeout": config.timeout,
            "retry_attempts": config.retry_attempts,
            "enable_logging": config.enable_logging,
            "user_agent": config.user_agent,
            "max_connections": config.max_connections,
            "rate_limit_delay": config.rate_limit_delay,
            "circuit_breaker_enabled": config.circuit_breaker_enabled,
            "circuit_config": config.get_circuit_config(),
            "enable_health_monitoring": config.enable_health_monitoring,
            "enable_metrics_collection": config.enable_metrics_collection,
        }

        # Apply any overrides from kwargs
        client_kwargs.update(kwargs)

        # Filter out None values and unknown parameters
        filtered_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}

        return cls(**filtered_kwargs)

    @classmethod
    def from_config(
            cls, config: OutlineClientConfig, **kwargs: Any
    ) -> AsyncOutlineClient:
        """
        Create AsyncOutlineClient from OutlineClientConfig object.

        Args:
            config: Pre-configured OutlineClientConfig instance
            **kwargs: Additional client options (override config settings)

        Returns:
            Configured AsyncOutlineClient instance

        Examples:
            Basic usage::

                config = OutlineClientConfig.from_env()
                async with AsyncOutlineClient.from_config(config) as client:
                    keys = await client.get_access_keys()
        """
        client_kwargs = {
            "api_url": config.api_url,
            "cert_sha256": config.cert_sha256,
            "json_format": config.json_format,
            "timeout": config.timeout,
            "retry_attempts": config.retry_attempts,
            "enable_logging": config.enable_logging,
            "user_agent": config.user_agent,
            "max_connections": config.max_connections,
            "rate_limit_delay": config.rate_limit_delay,
            "circuit_breaker_enabled": config.circuit_breaker_enabled,
            "circuit_config": config.get_circuit_config(),
            "enable_health_monitoring": config.enable_health_monitoring,
            "enable_metrics_collection": config.enable_metrics_collection,
        }

        # Apply any overrides from kwargs
        client_kwargs.update(kwargs)

        # Filter out None values
        filtered_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}

        return cls(**filtered_kwargs)

    # Add methods to the class
    AsyncOutlineClient.from_env = from_env
    AsyncOutlineClient.from_config = from_config


# Example usage and testing
if __name__ == "__main__":
    # Create environment template
    create_env_template()

    try:
        # Test configuration loading (with required=False for demo)
        config = OutlineClientConfig.from_env(required=False)
        print("✓ Configuration loaded successfully:")
        print(f"  {config}")
        print(f"  Circuit breaker enabled: {config.circuit_breaker_enabled}")
        print(f"  Health monitoring enabled: {config.enable_health_monitoring}")

        # Add methods to AsyncOutlineClient
        _add_from_env_method()
        print("✓ Added from_env() and from_config() methods to AsyncOutlineClient")

        # Example of creating client from environment
        # (This would require actual environment variables to work)
        print("\nExample usage:")
        print("# Load from environment variables")
        print("client = AsyncOutlineClient.from_env()")
        print("")
        print("# Load from custom .env file")
        print("client = AsyncOutlineClient.from_env(env_file='.env.production')")
        print("")
        print("# Load with custom prefix")
        print("client = AsyncOutlineClient.from_env(prefix='PROD_OUTLINE_')")

    except ConfigurationError as e:
        print(f"✗ Configuration error: {e}")
        print("\nTo test with real configuration, set these environment variables:")
        print("export OUTLINE_API_URL=https://your-server.com:port/secret")
        print("export OUTLINE_CERT_SHA256=your-certificate-fingerprint")

    except Exception as e:
        print(f"✗ Unexpected error: {e}")

# Auto-integrate when module is imported
try:
    _add_from_env_method()
except ImportError:
    # Client not available yet, will be added when client module is imported
    pass