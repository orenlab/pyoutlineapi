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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Union, Optional, TYPE_CHECKING
from urllib.parse import urlparse

from pydantic import BaseModel

from .api_mixins import (
    ServerManagementMixin,
    MetricsMixin,
    AccessKeyMixin,
    DataLimitMixin,
    BatchOperationsMixin,
)
from .base_client import BaseHTTPClient
from .circuit_breaker import CircuitConfig
from .common_types import Constants, CommonValidators
from .config import OutlineClientConfig
from .health_monitoring import HealthMonitoringMixin
from .response_parser import ResponseParser, JsonDict

if TYPE_CHECKING:
    from .exceptions import APIError, CircuitOpenError, ConfigurationError

logger = logging.getLogger(__name__)


class AsyncOutlineClient(
    BaseHTTPClient,
    ServerManagementMixin,
    MetricsMixin,
    AccessKeyMixin,
    DataLimitMixin,
    BatchOperationsMixin,
    HealthMonitoringMixin,
):
    """
    Asynchronous client for the Outline VPN Server API.

    This client provides a comprehensive, production-ready interface for managing
    Outline VPN servers with built-in circuit breaker protection, health monitoring,
    performance metrics, and robust error handling.

    Features:
        - Circuit breaker pattern for resilient API calls
        - Health monitoring with detailed metrics
        - Batch operations for efficient bulk management
        - Environment-based configuration
        - Comprehensive error handling and retry logic
        - SSL certificate validation
        - Rate limiting and connection pooling

    Args:
        api_url: Base URL for the Outline server API (e.g., "https://server.com:12345/secret")
        cert_sha256: SHA-256 fingerprint of the server's TLS certificate (64 hex characters)
        json_format: Return raw JSON instead of Pydantic models (default: False)
        timeout: Request timeout in seconds (default: 30)
        retry_attempts: Number of retry attempts for failed requests (default: 3)
        enable_logging: Enable debug logging for API calls (default: False)
        user_agent: Custom user agent string (default: "PyOutlineAPI/0.4.0")
        max_connections: Maximum number of connections in pool (default: 10)
        rate_limit_delay: Minimum delay between requests in seconds (default: 0.0)
        circuit_breaker_enabled: Enable circuit breaker protection (default: True)
        circuit_config: Custom circuit breaker configuration
        enable_health_monitoring: Enable health monitoring features (default: True)
        enable_metrics_collection: Enable performance metrics collection (default: True)

    Examples:
        Basic usage with context manager (recommended):

        >>> async def manage_outline_server():
        ...     async with AsyncOutlineClient(
        ...         "https://outline.example.com:12345/secret",
        ...         "a1b2c3d4e5f6789abcdef1234567890abcdef1234567890abcdef1234567890ab"
        ...     ) as client:
        ...         # Get server information
        ...         server = await client.get_server_info()
        ...         print(f"Server: {server.name} (version {server.version})")
        ...
        ...         # Create a new access key
        ...         key = await client.create_access_key(name="Alice")
        ...         print(f"Created key for {key.name}: {key.access_url}")
        ...
        ...         # Check server health
        ...         health = await client.health_check()
        ...         print(f"Server healthy: {health['healthy']}")

        Load configuration from environment variables:

        >>> async def use_environment_config():
        ...     import os
        ...     os.environ["OUTLINE_API_URL"] = "https://your-server.com:port/secret"
        ...     os.environ["OUTLINE_CERT_SHA256"] = "your-cert-fingerprint"
        ...
        ...     async with AsyncOutlineClient.from_env() as client:
        ...         keys = await client.get_access_keys()
        ...         print(f"Found {keys.count} access keys")

        Custom configuration with resilient settings:

        >>> async def create_resilient_outline_client():
        ...     config = CircuitConfig(
        ...         failure_threshold=3,
        ...         recovery_timeout=30.0,
        ...         failure_rate_threshold=0.7
        ...     )
        ...
        ...     async with AsyncOutlineClient(
        ...         api_url="https://outline.example.com:12345/secret",
        ...         cert_sha256="your-cert-fingerprint",
        ...         circuit_config=config,
        ...         timeout=60,
        ...         retry_attempts=5,
        ...         enable_logging=True
        ...     ) as client:
        ...         # Client is configured for unreliable networks
        ...         summary = await client.get_server_summary()
        ...         print(f"Server has {summary['access_keys_count']} keys")

        Batch operations for efficient management:

        >>> async def perform_batch_operations():
        ...     async with AsyncOutlineClient.from_env() as client:
        ...         # Create multiple keys at once
        ...         key_configs = [
        ...             {"name": "Alice", "port": 8001},
        ...             {"name": "Bob", "port": 8002},
        ...             {"name": "Charlie"}  # Will use default port
        ...         ]
        ...
        ...         results = await client.batch_create_access_keys(
        ...             key_configs,
        ...             max_concurrent=3
        ...         )
        ...
        ...         # Check results
        ...         successful_keys = [r for r in results if not isinstance(r, Exception)]
        ...         print(f"Created {len(successful_keys)} keys successfully")

        Health monitoring and metrics:

        >>> async def monitor_outline_server_health():
        ...     async with AsyncOutlineClient.from_env() as client:
        ...         # Get comprehensive health status
        ...         health = await client.get_detailed_health_status()
        ...
        ...         if not health["healthy"]:
        ...             for check_name, check_result in health["checks"].items():
        ...                 if check_result["status"] != "healthy":
        ...                     print(f"Issue with {check_name}: {check_result['message']}")
        ...
        ...         # Get performance metrics
        ...         metrics = client.get_performance_metrics()
        ...         print(f"Success rate: {metrics['success_rate']:.1%}")
        ...         print(f"Average response time: {metrics['avg_response_time']:.3f}s")
        ...
        ...         # Wait for service to become healthy
        ...         if await client.wait_for_healthy_state(timeout=120):
        ...             print("Service is healthy and ready")

        Using the factory method for one-shot operations:

        >>> async def perform_quick_outline_operation():
        ...     async with AsyncOutlineClient.create(
        ...         "https://outline.example.com:12345/secret",
        ...         "your-cert-fingerprint",
        ...         enable_logging=True
        ...     ) as client:
        ...         # Perform quick operations
        ...         keys = await client.get_access_keys()
        ...         return keys.count

        Error handling with circuit breaker awareness:

        >>> async def handle_outline_client_errors():
        ...     async with AsyncOutlineClient.from_env() as client:
        ...         try:
        ...             # Protected operation
        ...             async with client.circuit_protected_operation():
        ...                 server = await client.get_server_info()
        ...
        ...         except CircuitOpenError as e:
        ...             print(f"Service unavailable, retry after {e.retry_after}s")
        ...
        ...         except APIError as e:
        ...             print(f"API error {e.status_code}: {e}")
        ...
        ...         # Check circuit breaker status
        ...         cb_status = await client.get_circuit_breaker_status()
        ...         if cb_status["enabled"]:
        ...             print(f"Circuit breaker state: {cb_status['state']}")

    Raises:
        ValueError: If URL or certificate fingerprint format is invalid
        ConfigurationError: If configuration parameters are invalid
        APIError: If API requests fail
        CircuitOpenError: If circuit breaker is open
    """

    def __init__(
            self,
            api_url: str,
            cert_sha256: str,
            *,
            json_format: bool = False,
            timeout: int = Constants.DEFAULT_TIMEOUT,
            retry_attempts: int = Constants.DEFAULT_RETRY_ATTEMPTS,
            enable_logging: bool = False,
            user_agent: str | None = None,
            max_connections: int = Constants.DEFAULT_MAX_CONNECTIONS,
            rate_limit_delay: float = 0.0,
            circuit_breaker_enabled: bool = True,
            circuit_config: CircuitConfig | None = None,
            enable_health_monitoring: bool = True,
            enable_metrics_collection: bool = True,
    ) -> None:
        # Validate inputs early
        validated_url = CommonValidators.validate_url(api_url)
        validated_cert = CommonValidators.validate_cert_fingerprint(cert_sha256)

        # Store client-specific configuration
        self._json_format = json_format

        # Initialize base client with validated inputs
        super().__init__(
            api_url=validated_url,
            cert_sha256=validated_cert,
            timeout=timeout,
            retry_attempts=retry_attempts,
            enable_logging=enable_logging,
            user_agent=user_agent or Constants.DEFAULT_USER_AGENT,
            max_connections=max_connections,
            rate_limit_delay=rate_limit_delay,
            circuit_breaker_enabled=circuit_breaker_enabled,
            circuit_config=circuit_config,
            enable_health_monitoring=enable_health_monitoring,
            enable_metrics_collection=enable_metrics_collection,
        )

        # Initialize health monitoring
        self.__initialize_health_monitoring(
            enable_health_monitoring=enable_health_monitoring,
            enable_metrics_collection=enable_metrics_collection,
        )

        if enable_logging:
            logger.info(
                f"Outline client initialized for {self.api_url} "
                f"with circuit breaker: {circuit_breaker_enabled}"
            )

    def __initialize_health_monitoring(
            self,
            enable_health_monitoring: bool = True,
            enable_metrics_collection: bool = True,
    ) -> None:
        """Initialize health monitoring components (private method)."""
        # Call the mixin initialization
        self._initialize_health_monitoring(
            enable_health_monitoring=enable_health_monitoring,
            enable_metrics_collection=enable_metrics_collection,
        )

    @classmethod
    @asynccontextmanager
    async def create(
            cls, api_url: str, cert_sha256: str, **kwargs: Any
    ) -> AsyncGenerator[AsyncOutlineClient, None]:
        """
        Factory method that returns an async context manager.

        This is a convenience method that creates and properly initializes
        the client in a single operation. The client will be automatically
        connected and cleaned up when exiting the context.

        Args:
            api_url: Base URL for the Outline server API
            cert_sha256: SHA-256 fingerprint of the server's TLS certificate
            **kwargs: Additional client configuration options

        Returns:
            Configured and connected AsyncOutlineClient instance

        Examples:
            Basic usage:

            >>> async def connect_to_outline_server():
            ...     async with AsyncOutlineClient.create(
            ...         "https://outline.example.com:12345/secret",
            ...         "a1b2c3d4e5f6789abcdef1234567890abcdef1234567890abcdef1234567890ab"
            ...     ) as client:
            ...         server = await client.get_server_info()
            ...         print(f"Connected to: {server.name}")

            With custom configuration:

            >>> async def create_outline_client_with_custom_settings():
            ...     async with AsyncOutlineClient.create(
            ...         api_url="https://outline.example.com:12345/secret",
            ...         cert_sha256="your-cert-fingerprint",
            ...         enable_logging=True,
            ...         timeout=60,
            ...         circuit_breaker_enabled=False
            ...     ) as client:
            ...         # Client is ready to use
            ...         keys = await client.get_access_keys()
        """
        client = cls(api_url, cert_sha256, **kwargs)
        async with client:
            yield client

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
        and creates a properly configured client instance. It's the recommended
        way to configure the client for production deployments.

        Environment Variables:
            Required (when required=True):
                OUTLINE_API_URL: Outline server API URL
                OUTLINE_CERT_SHA256: Server certificate SHA-256 fingerprint

            Optional configuration:
                OUTLINE_JSON_FORMAT: Return raw JSON (default: false)
                OUTLINE_TIMEOUT: Request timeout in seconds (default: 30)
                OUTLINE_RETRY_ATTEMPTS: Retry attempts (default: 3)
                OUTLINE_ENABLE_LOGGING: Enable debug logging (default: false)
                OUTLINE_CIRCUIT_BREAKER_ENABLED: Enable circuit breaker (default: true)
                OUTLINE_ENABLE_HEALTH_MONITORING: Enable health monitoring (default: true)
                And many more - see OutlineClientConfig.from_env() for full list

        Args:
            prefix: Environment variable prefix (default: "OUTLINE_")
            required: Require mandatory variables or use safe defaults for testing
            env_file: Path to .env file to load variables from
            validate_connection: Validate connection settings on startup
            **kwargs: Additional client options (override env settings)

        Returns:
            Configured AsyncOutlineClient instance (not connected - use as context manager)

        Raises:
            ConfigurationError: If configuration is invalid or required vars are missing

        Examples:
            Basic usage with .env file:

            >>> async def load_config_from_env():
            ...     # Create .env file first
            ...     import pyoutlineapi
            ...     pyoutlineapi.create_config_template(".env")
            ...     # Edit .env with your settings, then:
            ...
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         server = await client.get_server_info()
            ...         print(f"Server: {server.name}")

            Custom environment prefix for multiple environments:

            >>> async def use_custom_env_prefix():
            ...     import os
            ...     os.environ["PROD_OUTLINE_API_URL"] = "https://prod-server.com/secret"
            ...     os.environ["PROD_OUTLINE_CERT_SHA256"] = "prod-cert-fingerprint"
            ...
            ...     async with AsyncOutlineClient.from_env(prefix="PROD_OUTLINE_") as client:
            ...         # Using production configuration
            ...         health = await client.health_check()

            Load from custom .env file:

            >>> async def load_from_custom_env_file():
            ...     async with AsyncOutlineClient.from_env(
            ...         env_file=".env.production"
            ...     ) as client:
            ...         summary = await client.get_server_summary()

            Override specific settings:

            >>> async def override_env_settings():
            ...     async with AsyncOutlineClient.from_env(
            ...         enable_logging=True,  # Override env setting
            ...         timeout=60,           # Override env setting
            ...         required=False        # Use defaults for missing vars
            ...     ) as client:
            ...         keys = await client.get_access_keys()

            Testing with safe defaults:

            >>> async def test_with_safe_defaults():
            ...     # For testing when environment vars are not set
            ...     async with AsyncOutlineClient.from_env(required=False) as client:
            ...         # Client uses safe default values
            ...         # (won't actually connect to a real server)
            ...         pass
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

        # Filter out None values
        filtered_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}

        return cls(**filtered_kwargs)

    @classmethod
    def from_config(
            cls, config: OutlineClientConfig, **kwargs: Any
    ) -> AsyncOutlineClient:
        """
        Create AsyncOutlineClient from OutlineClientConfig object.

        This factory method allows you to create a client from a pre-configured
        configuration object, which is useful when you need to validate or
        modify configuration before creating the client.

        Args:
            config: Pre-configured OutlineClientConfig instance
            **kwargs: Additional client options (override config settings)

        Returns:
            Configured AsyncOutlineClient instance (not connected - use as context manager)

        Examples:
            Basic usage:

            >>> async def create_from_config():
            ...     config = OutlineClientConfig.from_env()
            ...     async with AsyncOutlineClient.from_config(config) as client:
            ...         keys = await client.get_access_keys()

            Override specific config settings:

            >>> async def override_config_settings():
            ...     config = OutlineClientConfig.from_env()
            ...     async with AsyncOutlineClient.from_config(
            ...         config,
            ...         enable_logging=True,  # Override config setting
            ...         timeout=120          # Override config setting
            ...     ) as client:
            ...         # Client uses config settings with overrides
            ...         server = await client.get_server_info()

            Validate config before use:

            >>> async def validate_config_before_use():
            ...     try:
            ...         config = OutlineClientConfig.from_env()
            ...         print(f"Configuration loaded: {config}")
            ...
            ...         async with AsyncOutlineClient.from_config(config) as client:
            ...             health = await client.health_check()
            ...
            ...     except ConfigurationError as e:
            ...         print(f"Configuration error: {e}")
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

    # Enhanced utility methods

    async def get_server_summary(self, metrics_since: str = "24h") -> dict[str, Any]:
        """
        Get comprehensive server summary including info, metrics, and key count.

        This method provides a one-stop overview of your Outline server,
        combining server information, access key statistics, and metrics
        if available. It's perfect for dashboard displays or health checks.

        Args:
            metrics_since: Time range for experimental metrics (default: "24h")
                          Valid values: "1h", "24h", "7d", "30d"

        Returns:
            Dictionary with comprehensive server information:
                - server: Server configuration and details
                - access_keys_count: Number of access keys
                - access_keys: List of key summaries (id, name, port)
                - transfer_metrics: Data transfer metrics if available
                - experimental_metrics: Detailed metrics if available
                - healthy: Overall health status
                - timestamp: When the summary was generated

        Examples:
            Get basic server overview:

            >>> async def get_basic_server_overview():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         summary = await client.get_server_summary()
            ...
            ...         print(f"Server: {summary['server']['name']}")
            ...         print(f"Keys: {summary['access_keys_count']}")
            ...         print(f"Healthy: {summary['healthy']}")
            ...
            ...         if 'total_data_transferred' in summary:
            ...             gb_transferred = summary['total_data_transferred'] / (1024**3)
            ...             print(f"Data transferred: {gb_transferred:.2f} GB")

            Get detailed metrics for the last 7 days:

            >>> async def get_detailed_server_metrics():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         summary = await client.get_server_summary("7d")
            ...
            ...         if summary['experimental_metrics']:
            ...             server_metrics = summary['experimental_metrics']['server']
            ...             locations = server_metrics['locations']
            ...             print(f"Connections from {len(locations)} locations")

            Monitor server health:

            >>> async def monitor_server_health_status():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         summary = await client.get_server_summary()
            ...
            ...         if not summary['healthy']:
            ...             print(f"Server issue: {summary.get('error', 'Unknown')}")
            ...             return False
            ...
            ...         # Check individual access keys
            ...         for key_info in summary['access_keys']:
            ...             print(f"Key {key_info['name']}: Port {key_info['port']}")
        """
        summary: dict[str, Any] = {}

        try:
            # Get basic server info
            server_info = await self.get_server_info()
            summary["server"] = (
                server_info.model_dump()
                if isinstance(server_info, BaseModel)
                else server_info
            )

            # Get access keys count and details
            keys = await self.get_access_keys()
            if isinstance(keys, BaseModel):
                summary["access_keys_count"] = keys.count
                summary["access_keys"] = [
                    {"id": key.id, "name": key.name, "port": key.port}
                    for key in keys.access_keys
                ]
            else:
                key_list = keys.get("accessKeys", [])
                summary["access_keys_count"] = len(key_list)
                summary["access_keys"] = [
                    {
                        "id": key.get("id"),
                        "name": key.get("name"),
                        "port": key.get("port"),
                    }
                    for key in key_list
                ]

            # Get metrics if available
            try:
                metrics_status = await self.get_metrics_status()
                metrics_enabled = (
                    metrics_status.metrics_enabled
                    if isinstance(metrics_status, BaseModel)
                    else metrics_status.get("metricsEnabled", False)
                )

                if metrics_enabled:
                    # Get transfer metrics
                    transfer_metrics = await self.get_transfer_metrics()
                    if isinstance(transfer_metrics, BaseModel):
                        summary["transfer_metrics"] = transfer_metrics.model_dump()
                        summary["total_data_transferred"] = (
                            transfer_metrics.total_bytes_transferred
                        )
                    else:
                        summary["transfer_metrics"] = transfer_metrics
                        # Calculate total manually for JSON response
                        bytes_by_user = transfer_metrics.get(
                            "bytesTransferredByUserId", {}
                        )
                        summary["total_data_transferred"] = sum(bytes_by_user.values())

                    # Try to get experimental metrics
                    try:
                        experimental_metrics = await self.get_experimental_metrics(
                            metrics_since
                        )
                        summary["experimental_metrics"] = (
                            experimental_metrics.model_dump()
                            if isinstance(experimental_metrics, BaseModel)
                            else experimental_metrics
                        )
                    except Exception as exp_error:
                        summary["experimental_metrics"] = None
                        summary["experimental_metrics_error"] = str(exp_error)
                else:
                    summary["transfer_metrics"] = None
                    summary["experimental_metrics"] = None
                    summary["metrics_disabled"] = True

            except Exception as metrics_error:
                summary["transfer_metrics"] = None
                summary["experimental_metrics"] = None
                summary["metrics_error"] = str(metrics_error)

            # Add health status
            summary["healthy"] = True
            summary["timestamp"] = __import__("time").time()

        except Exception as e:
            summary["healthy"] = False
            summary["error"] = str(e)
            summary["timestamp"] = __import__("time").time()

        return summary

    def configure_logging(
            self, level: str = "INFO", format_string: str | None = None
    ) -> None:
        """
        Configure logging for the client.

        This method allows you to dynamically configure logging for the client
        instance, which is useful for debugging or changing log levels at runtime.

        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
            format_string: Custom format string for log messages

        Examples:
            Enable debug logging:

            >>> async def enable_debug_logging():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         client.configure_logging("DEBUG")
            ...
            ...         # Now all API calls will be logged with debug info
            ...         server = await client.get_server_info()

            Custom log format:

            >>> async def set_custom_log_format():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         client.configure_logging(
            ...             "INFO",
            ...             "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            ...         )
            ...
            ...         keys = await client.get_access_keys()
        """
        # Enable logging if not already enabled
        self._enable_logging = True

        # Get the main pyoutlineapi logger (parent of all loggers in the package)
        pyoutline_logger = logging.getLogger("pyoutlineapi")

        # Clear existing handlers to avoid duplicates
        for handler in pyoutline_logger.handlers[:]:
            pyoutline_logger.removeHandler(handler)

        # Create new handler with custom format
        handler = logging.StreamHandler()
        if format_string:
            formatter = logging.Formatter(format_string)
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        handler.setFormatter(formatter)

        # Configure the main logger
        pyoutline_logger.addHandler(handler)
        pyoutline_logger.setLevel(getattr(logging, level.upper()))
        pyoutline_logger.propagate = False  # Prevent propagation to root logger

        logger.info(f"Logging reconfigured: level={level}, format_updated={format_string is not None}")

    def configure_circuit_breaker(
            self,
            failure_threshold: int | None = None,
            recovery_timeout: float | None = None,
            success_threshold: int | None = None,
            failure_rate_threshold: float | None = None,
    ) -> None:
        """
        Dynamically reconfigure circuit breaker parameters.

        This method allows you to adjust circuit breaker settings at runtime,
        which can be useful for adapting to changing network conditions or
        server performance characteristics.

        Note: This creates a new circuit breaker with updated configuration.
        The old circuit breaker state and metrics are not preserved.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before trying half-open state (seconds)
            success_threshold: Successes needed in half-open to close circuit
            failure_rate_threshold: Failure rate threshold to open circuit (0.0-1.0)

        Examples:
            Make circuit breaker more sensitive for unreliable networks:

            >>> async def configure_sensitive_circuit_breaker():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         # Default settings may be too tolerant
            ...         client.configure_circuit_breaker(
            ...             failure_threshold=3,        # Open after 3 failures
            ...             recovery_timeout=30.0,      # Try recovery after 30s
            ...             failure_rate_threshold=0.3  # Open at 30% failure rate
            ...         )
            ...
            ...         # Circuit breaker is now more sensitive
            ...         server = await client.get_server_info()

            Make circuit breaker more tolerant for testing:

            >>> async def configure_tolerant_circuit_breaker():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         client.configure_circuit_breaker(
            ...             failure_threshold=10,       # Allow more failures
            ...             recovery_timeout=60.0,      # Wait longer for recovery
            ...             failure_rate_threshold=0.8  # Only open at 80% failure rate
            ...         )
            ...
            ...         # Circuit breaker is now more tolerant
            ...         keys = await client.get_access_keys()
        """
        if not self._circuit_breaker:
            logger.warning("Circuit breaker not enabled, cannot reconfigure")
            return

        # Create new config with updated values
        old_config = self._circuit_breaker.config
        new_config = CircuitConfig(
            failure_threshold=failure_threshold or old_config.failure_threshold,
            recovery_timeout=recovery_timeout or old_config.recovery_timeout,
            success_threshold=success_threshold or old_config.success_threshold,
            failure_rate_threshold=failure_rate_threshold
                                   or old_config.failure_rate_threshold,
            call_timeout=old_config.call_timeout,
            min_calls_to_evaluate=old_config.min_calls_to_evaluate,
            sliding_window_size=old_config.sliding_window_size,
            exponential_backoff_multiplier=old_config.exponential_backoff_multiplier,
            max_recovery_timeout=old_config.max_recovery_timeout,
        )

        # Schedule circuit breaker recreation
        import asyncio

        asyncio.create_task(self.__recreate_circuit_breaker(new_config))

        logger.info("Circuit breaker reconfiguration scheduled")

    async def __recreate_circuit_breaker(self, new_config: CircuitConfig) -> None:
        """Recreate circuit breaker with new configuration (private method)."""
        if self._circuit_breaker:
            await self._circuit_breaker.stop()

        from .circuit_breaker import AsyncCircuitBreaker

        self._circuit_breaker = AsyncCircuitBreaker(
            name=f"outline-api-{urlparse(self._api_url).netloc}",
            config=new_config,
            health_checker=getattr(self, "_health_checker", None),
        )

        # Setup monitoring callbacks if metrics collection is enabled
        if (
                hasattr(self, "_enable_metrics_collection")
                and self._enable_metrics_collection
        ):
            self._setup_monitoring_callbacks()

        await self._circuit_breaker.start()
        logger.info("Circuit breaker recreated with new configuration")

    # Enhanced utility methods for working with responses

    async def parse_response(
            self,
            response_data: dict[str, Any],
            model_class: type[BaseModel],
            as_json: bool | None = None,
    ) -> Union[JsonDict, BaseModel]:
        """
        Parse response data using specified model.

        This utility method allows you to manually parse API response data
        using any of the available Pydantic models. It's useful when you
        need to parse responses from custom API calls or when working with
        raw response data.

        Args:
            response_data: Response data to parse
            model_class: Pydantic model class for validation
            as_json: Override default json_format setting

        Returns:
            Parsed and validated response data (Pydantic model or JSON dict)

        Examples:
            Parse server info response manually:

            >>> async def parse_server_info_manually():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         # Get raw response
            ...         raw_response = await client.request("GET", "server")
            ...
            ...         # Parse using model
            ...         server = await client.parse_response(raw_response, Server)
            ...         print(f"Server name: {server.name}")

            Parse as JSON regardless of client setting:

            >>> async def parse_as_json_format():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         raw_response = await client.request("GET", "access-keys")
            ...
            ...         # Force JSON format
            ...         keys_json = await client.parse_response(
            ...             raw_response, AccessKeyList, as_json=True
            ...         )
            ...         print(f"Keys: {keys_json}")
        """
        json_format = as_json if as_json is not None else self._json_format
        return await ResponseParser.parse_response_data(
            response_data, model_class, json_format
        )

    # Enhanced management methods

    async def get_detailed_health_status(self) -> dict[str, Any]:
        """
        Get comprehensive health status including all subsystems.

        This method provides a detailed health check that includes individual
        component status, performance metrics, circuit breaker state, and
        connectivity information. It's ideal for monitoring dashboards and
        automated health checks.

        Returns:
            Detailed health status with individual component checks:
                - healthy: Overall health status (bool)
                - timestamp: When the check was performed
                - checks: Individual component check results
                - detailed_metrics: Performance metrics (if requested)
                - circuit_breaker_status: Circuit breaker information

        Examples:
            Basic health monitoring:

            >>> async def perform_basic_health_monitoring():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         health = await client.get_detailed_health_status()
            ...
            ...         if health["healthy"]:
            ...             print("✅ Service is healthy")
            ...         else:
            ...             print("❌ Service has issues:")
            ...             for check_name, check_result in health["checks"].items():
            ...                 if check_result["status"] != "healthy":
            ...                     print(f"  - {check_name}: {check_result['message']}")

            Detailed monitoring with performance metrics:

            >>> async def detailed_performance_monitoring():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         health = await client.get_detailed_health_status()
            ...
            ...         # Check connectivity
            ...         conn_check = health["checks"].get("connectivity", {})
            ...         print(f"API connectivity: {conn_check.get('status', 'unknown')}")
            ...
            ...         # Check performance
            ...         perf_check = health["checks"].get("performance", {})
            ...         if perf_check.get("success_rate"):
            ...             rate = perf_check["success_rate"]
            ...             print(f"Success rate: {rate:.1%}")
            ...
            ...         # Check circuit breaker
            ...         cb_check = health["checks"].get("circuit_breaker", {})
            ...         if cb_check:
            ...             print(f"Circuit breaker: {cb_check.get('state', 'unknown')}")

            Automated health monitoring:

            >>> async def automated_health_monitoring():
            ...     import asyncio
            ...
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         while True:
            ...             try:
            ...                 health = await client.get_detailed_health_status()
            ...
            ...                 if not health["healthy"]:
            ...                     # Send alert
            ...                     failed_checks = [
            ...                         name for name, result in health["checks"].items()
            ...                         if result.get("status") != "healthy"
            ...                     ]
            ...                     print(f"⚠️  Health check failed: {failed_checks}")
            ...
            ...                 await asyncio.sleep(60)  # Check every minute
            ...
            ...             except Exception as e:
            ...                 print(f"Health check error: {e}")
            ...                 await asyncio.sleep(60)
        """
        return await self.health_check(include_detailed_metrics=True)

    async def wait_for_healthy_state(
            self, timeout: float = 60.0, check_interval: float = 5.0
    ) -> bool:
        """
        Wait for the client to reach a healthy state.

        This method continuously checks the service health until it becomes
        healthy or the timeout is reached. It's useful for startup sequences,
        deployment health checks, or waiting for service recovery.

        Args:
            timeout: Maximum time to wait in seconds (default: 60.0)
            check_interval: Time between health checks in seconds (default: 5.0)

        Returns:
            True if healthy state reached within timeout, False otherwise

        Examples:
            Wait for service to become healthy during startup:

            >>> async def wait_for_service_startup():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         print("Waiting for service to become healthy...")
            ...
            ...         if await client.wait_for_healthy_state(timeout=120):
            ...             print("✅ Service is healthy and ready")
            ...
            ...             # Proceed with operations
            ...             server = await client.get_server_info()
            ...             print(f"Connected to: {server.name}")
            ...         else:
            ...             print("❌ Service did not become healthy within timeout")

            Custom check interval for frequent monitoring:

            >>> async def frequent_health_monitoring():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         # Check every 2 seconds for faster detection
            ...         healthy = await client.wait_for_healthy_state(
            ...             timeout=60.0,
            ...             check_interval=2.0
            ...         )
            ...
            ...         if healthy:
            ...             print("Service recovered quickly!")

            Integration with deployment scripts:

            >>> async def verify_deployment():
            ...     # ... perform deployment steps ...
            ...
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         print("Verifying deployment health...")
            ...
            ...         if await client.wait_for_healthy_state(timeout=300):
            ...             print("✅ Deployment successful")
            ...             return True
            ...         else:
            ...             print("❌ Deployment failed health check")
            ...             return False
        """
        import asyncio
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                health = await self.health_check()
                if health["healthy"]:
                    return True
            except Exception as e:
                logger.debug(f"Health check failed during wait: {e}")

            await asyncio.sleep(check_interval)

        return False

    # Convenience properties

    @property
    def json_format(self) -> bool:
        """
        Get current JSON format setting.

        Returns:
            True if client returns raw JSON, False if it returns Pydantic models

        Examples:
            Check current format setting:

            >>> async def check_format_setting():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         if client.json_format:
            ...             print("Client returns JSON dictionaries")
            ...         else:
            ...             print("Client returns Pydantic models")
        """
        return self._json_format

    @json_format.setter
    def json_format(self, value: bool) -> None:
        """
        Set JSON format preference.

        Args:
            value: True to return raw JSON, False to return Pydantic models

        Examples:
            Change format at runtime:

            >>> async def change_format_at_runtime():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         # Initially returns Pydantic models
            ...         server = await client.get_server_info()
            ...         print(type(server))  # <class 'Server'>
            ...
            ...         # Switch to JSON format
            ...         client.json_format = True
            ...         server_json = await client.get_server_info()
            ...         print(type(server_json))  # <class 'dict'>
        """
        self._json_format = bool(value)

    @property
    def server_url(self) -> str:
        """
        Get the server URL without path or sensitive information.

        Returns:
            Server URL in format "https://hostname:port" (without secret path)

        Examples:
            Display connection info:

            >>> async def display_connection_info():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         print(f"Connected to: {client.server_url}")
            ...         # Output: Connected to: https://outline.example.com:12345
        """
        return self.api_url

    @property
    def connection_info(self) -> dict[str, Any]:
        """
        Get comprehensive connection information.

        Returns:
            Dictionary with connection details:
                - server_url: Server URL (without sensitive parts)
                - connected: Whether client is currently connected
                - circuit_breaker_enabled: Circuit breaker status
                - circuit_state: Current circuit breaker state
                - json_format: Response format setting

        Examples:
            Display connection status:

            >>> async def display_connection_status():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         info = client.connection_info
            ...         print(f"Server: {info['server_url']}")
            ...         print(f"Connected: {info['connected']}")
            ...         print(f"Circuit breaker: {info['circuit_state']}")

            Check connection before operations:

            >>> async def check_connection_before_operations():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         info = client.connection_info
            ...
            ...         if not info['connected']:
            ...             print("Warning: Client not connected")
            ...             return
            ...
            ...         if info['circuit_state'] == 'OPEN':
            ...             print("Warning: Circuit breaker is open")
            ...             return
            ...
            ...         # Safe to proceed
            ...         keys = await client.get_access_keys()
        """
        return {
            "server_url": self.server_url,
            "connected": self.is_connected,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "circuit_state": self.circuit_state,
            "json_format": self.json_format,
        }

    # Context manager support

    async def __aenter__(self) -> AsyncOutlineClient[BaseHTTPClient]:
        """
        Enter async context manager.

        This method is called when entering an 'async with' block.
        It initializes the HTTP session and starts the circuit breaker
        and health monitoring systems.

        Returns:
            The connected client instance

        Examples:
            Standard context manager usage:

            >>> async def standard_context_manager_usage():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         # Client is connected and ready
            ...         server = await client.get_server_info()
            ...         # Client will be automatically cleaned up on exit
        """
        return await super().__aenter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Exit async context manager.

        This method is called when exiting an 'async with' block.
        It properly shuts down the circuit breaker, health monitoring,
        and closes the HTTP session.

        Args:
            exc_type: Exception type (if any exception occurred)
            exc_val: Exception value (if any exception occurred)
            exc_tb: Exception traceback (if any exception occurred)

        Examples:
            Automatic cleanup:

            >>> async def automatic_cleanup_example():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         try:
            ...             keys = await client.get_access_keys()
            ...         except Exception as e:
            ...             print(f"Error: {e}")
            ...         # Client resources are automatically cleaned up here
        """
        await super().__aexit__(exc_type, exc_val, exc_tb)

    def __repr__(self) -> str:
        """
        Enhanced string representation of the client.

        Returns:
            Detailed string representation including connection status,
            circuit breaker state, and health information

        Examples:
            Display client status:

            >>> async def display_client_status():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         print(repr(client))
            ...         # Output: AsyncOutlineClient(url=https://server.com:12345,
            ...         #         status=connected, json_format=False, circuit=CLOSED, healthy)
        """
        status = "connected" if self.is_connected else "disconnected"
        cb_status = (
            f", circuit={self.circuit_state}" if self.circuit_breaker_enabled else ""
        )
        health_status = (
            ", healthy" if hasattr(self, "is_healthy") and self.is_healthy else ""
        )

        return (
            f"AsyncOutlineClient("
            f"url={self.server_url}, "
            f"status={status}, "
            f"json_format={self.json_format}"
            f"{cb_status}"
            f"{health_status})"
        )

    def __str__(self) -> str:
        """
        User-friendly string representation.

        Returns:
            Simple, user-friendly description of the client

        Examples:
            Display user-friendly client info:

            >>> async def display_user_friendly_info():
            ...     async with AsyncOutlineClient.from_env() as client:
            ...         print(str(client))
            ...         # Output: Outline API Client connected to https://server.com:12345
        """
        return f"Outline API Client connected to {self.server_url}"


# Convenience factory functions for common usage patterns
async def create_client_and_connect(
        api_url: str, cert_sha256: str, **kwargs: Any
) -> AsyncOutlineClient:
    """
    Create and connect a client in one step.

    This convenience function creates a client and immediately connects it,
    returning a connected client instance. Remember to properly clean up
    the client when done by using it as a context manager or calling
    the appropriate cleanup methods.

    Note: It's generally recommended to use the context manager approach
    with AsyncOutlineClient.create() instead of this function.

    Args:
        api_url: Base URL for the Outline server API
        cert_sha256: SHA-256 fingerprint of the server's TLS certificate
        **kwargs: Additional client configuration options

    Returns:
        Connected AsyncOutlineClient instance (requires manual cleanup)

    Examples:
        Quick connection (not recommended for production):

        >>> async def quick_connection_example():
        ...     client = await create_client_and_connect(
        ...         "https://outline.example.com:12345/secret",
        ...         "a1b2c3d4e5f6789abcdef1234567890abcdef1234567890abcdef1234567890ab"
        ...     )
        ...
        ...     try:
        ...         server = await client.get_server_info()
        ...         print(f"Connected to: {server.name}")
        ...     finally:
        ...         await client.__aexit__(None, None, None)  # Manual cleanup

        Better approach using context manager:

        >>> async def better_context_manager_approach():
        ...     async with AsyncOutlineClient.create(api_url, cert_sha256) as client:
        ...         server = await client.get_server_info()
        ...         print(f"Connected to: {server.name}")
        ...         # Automatic cleanup
    """
    client = AsyncOutlineClient(api_url, cert_sha256, **kwargs)
    await client.__aenter__()
    return client


def create_resilient_client(
        api_url: str, cert_sha256: str, **kwargs: Any
) -> AsyncOutlineClient:
    """
    Create a client with enhanced resilience settings.

    This factory configures the client with conservative settings that are
    suitable for unreliable networks, overloaded servers, or production
    environments where stability is more important than speed.

    Args:
        api_url: Base URL for the Outline server API
        cert_sha256: SHA-256 fingerprint of the server's TLS certificate
        **kwargs: Additional client configuration options (will override defaults)

    Returns:
        AsyncOutlineClient configured for maximum resilience (use as context manager)

    Examples:
        Basic resilient client:

        >>> async def basic_resilient_client_example():
        ...     async with create_resilient_client(
        ...         "https://outline.example.com:12345/secret",
        ...         "a1b2c3d4e5f6789abcdef1234567890abcdef1234567890abcdef1234567890ab"
        ...     ) as client:
        ...         # Client will be more tolerant of network issues
        ...         try:
        ...             keys = await client.get_access_keys()
        ...             print(f"Retrieved {keys.count} keys")
        ...         except CircuitOpenError as e:
        ...             print(f"Service temporarily unavailable, retry after {e.retry_after}s")

        Custom resilient settings:

        >>> async def custom_resilient_settings_example():
        ...     async with create_resilient_client(
        ...         api_url="https://outline.example.com:12345/secret",
        ...         cert_sha256="your-cert-fingerprint",
        ...         timeout=120,  # Even longer timeout
        ...         retry_attempts=7,  # More retries
        ...         enable_logging=True  # Debug logging
        ...     ) as client:
        ...         # Extremely tolerant client for very unreliable networks
        ...         server = await client.get_server_info()

        Monitor resilient client performance:

        >>> async def monitor_resilient_client_performance():
        ...     async with create_resilient_client(api_url, cert_sha256) as client:
        ...         # Check circuit breaker configuration
        ...         cb_status = await client.get_circuit_breaker_status()
        ...         print(f"Circuit breaker failure threshold: {cb_status['config']['failure_threshold']}")
        ...
        ...         # Perform operations
        ...         for i in range(10):
        ...             try:
        ...                 await client.get_server_info()
        ...                 print(f"Request {i+1}: ✅")
        ...             except Exception as e:
        ...                 print(f"Request {i+1}: ❌ {e}")
        ...
        ...         # Check performance metrics
        ...         metrics = client.get_performance_metrics()
        ...         print(f"Success rate: {metrics['success_rate']:.1%}")
    """
    resilient_defaults = {
        "timeout": 60,
        "retry_attempts": 5,
        "rate_limit_delay": 1.0,
        "circuit_breaker_enabled": True,
        "circuit_config": CircuitConfig(
            failure_threshold=3,
            recovery_timeout=30.0,
            success_threshold=2,
            failure_rate_threshold=0.7,  # More tolerant
            min_calls_to_evaluate=5,
        ),
        "enable_health_monitoring": True,
        "enable_metrics_collection": True,
    }

    # Merge provided kwargs with defaults (kwargs take precedence)
    config = {**resilient_defaults, **kwargs}

    return AsyncOutlineClient(api_url, cert_sha256, **config)
