"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Main async client with clean, intuitive API.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from .api_mixins import AccessKeyMixin, DataLimitMixin, MetricsMixin, ServerMixin
from .base_client import BaseHTTPClient
from .common_types import Validators
from .config import OutlineClientConfig
from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

logger = logging.getLogger(__name__)


class AsyncOutlineClient(
    BaseHTTPClient,
    ServerMixin,
    AccessKeyMixin,
    DataLimitMixin,
    MetricsMixin,
):
    """
    Async client for Outline VPN Server API.

    Features:
    - Clean, intuitive API for all Outline operations
    - Optional circuit breaker for resilience
    - Environment-based configuration
    - Type-safe responses with Pydantic models
    - Comprehensive error handling
    - Rate limiting and connection pooling

    Example:
        >>> from pyoutlineapi import AsyncOutlineClient
        >>>
        >>> # From environment variables
        >>> async with AsyncOutlineClient.from_env() as client:
        ...     server = await client.get_server_info()
        ...     keys = await client.get_access_keys()
        ...     print(f"Server: {server.name}, Keys: {keys.count}")
        >>>
        >>> # With direct parameters
        >>> async with AsyncOutlineClient.create(
        ...     api_url="https://server.com:12345/secret",
        ...     cert_sha256="abc123...",
        ... ) as client:
        ...     key = await client.create_access_key(name="Alice")
    """

    def __init__(
        self,
        config: OutlineClientConfig | None = None,
        *,
        api_url: str | None = None,
        cert_sha256: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize Outline client.

        Args:
            config: Pre-configured config object (preferred)
            api_url: Direct API URL (alternative to config)
            cert_sha256: Direct certificate (alternative to config)
            **kwargs: Additional options (timeout, retry_attempts, etc.)

        Raises:
            ConfigurationError: If neither config nor required parameters provided

        Example:
            >>> # With config object
            >>> config = OutlineClientConfig.from_env()
            >>> client = AsyncOutlineClient(config)
            >>>
            >>> # With direct parameters
            >>> client = AsyncOutlineClient(
            ...     api_url="https://server.com:12345/secret",
            ...     cert_sha256="abc123...",
            ...     timeout=60,
            ... )
        """
        # Handle different initialization methods with structural pattern matching
        match config, api_url, cert_sha256:
            # Case 1: No config, but both direct parameters provided
            case None, str() as url, str() as cert if url and cert:
                config = OutlineClientConfig.create_minimal(
                    api_url=url,
                    cert_sha256=cert,
                    **kwargs,
                )

            # Case 2: Config provided, no direct parameters
            case OutlineClientConfig(), None, None:
                # Valid configuration, proceed
                pass

            # Case 3: Missing required parameters
            case None, None, _:
                raise ConfigurationError("Missing required 'api_url' parameter")
            case None, _, None:
                raise ConfigurationError("Missing required 'cert_sha256' parameter")
            case None, None, None:
                raise ConfigurationError(
                    "Either provide 'config' or both 'api_url' and 'cert_sha256'"
                )

            # Case 4: Conflicting parameters
            case OutlineClientConfig(), str() | None, str() | None:
                raise ConfigurationError(
                    "Cannot specify both 'config' and direct parameters. "
                    "Use either config object or api_url/cert_sha256, but not both."
                )

            # Case 5: Unexpected input types
            case _:
                raise ConfigurationError(
                    f"Invalid parameter types: "
                    f"config={type(config).__name__}, "
                    f"api_url={type(Validators.sanitize_url_for_logging(api_url)).__name__}, "
                    f"cert_sha256=***MASKED*** [See config instead]"
                )

        # Store config
        self._config = config

        # Initialize base client
        super().__init__(
            api_url=config.api_url,
            cert_sha256=config.cert_sha256,
            timeout=config.timeout,
            retry_attempts=config.retry_attempts,
            max_connections=config.max_connections,
            enable_logging=config.enable_logging,
            circuit_config=config.circuit_config,
            rate_limit=config.rate_limit,
        )

        if config.enable_logging:
            safe_url = Validators.sanitize_url_for_logging(self.api_url)
            logger.info(f"Client initialized for {safe_url}")

    @property
    def config(self) -> OutlineClientConfig:
        """
        Get current configuration.

        ⚠️ SECURITY WARNING:
        This returns the full config object including sensitive data:
        - api_url with secret path
        - cert_sha256 (as SecretStr, but can be extracted)

        For logging or display, use get_sanitized_config() instead.

        Returns:
            OutlineClientConfig: Full configuration object with sensitive data

        Example:
            >>> # ❌ UNSAFE - may expose secrets in logs
            >>> print(client.config)
            >>> logger.info(f"Config: {client.config}")
            >>>
            >>> # ✅ SAFE - use sanitized version
            >>> print(client.get_sanitized_config())
            >>> logger.info(f"Config: {client.get_sanitized_config()}")
        """
        return self._config

    def get_sanitized_config(self) -> dict[str, Any]:
        """
        Get configuration with sensitive data masked.

        Safe for logging, debugging, error reporting, and display.

        Returns:
            dict: Configuration with masked sensitive values

        Example:
            >>> config_safe = client.get_sanitized_config()
            >>> logger.info(f"Client config: {config_safe}")
            >>> print(config_safe)
            {
                'api_url': 'https://server.com:12345/***',
                'cert_sha256': '***MASKED***',
                'timeout': 30,
                'retry_attempts': 3,
                ...
            }
        """
        return self._config.get_sanitized_config()

    @property
    def json_format(self) -> bool:
        """
        Get JSON format preference.

        Returns:
            bool: True if returning raw JSON dicts instead of models
        """
        return self._config.json_format

    def _resolve_json_format(self, as_json: bool | None) -> bool:
        """
        Resolve JSON format preference.

        If as_json is explicitly provided, uses that value.
        Otherwise, uses config.json_format from .env (OUTLINE_JSON_FORMAT).

        Args:
            as_json: Explicit preference (None = use config default)

        Returns:
            bool: Final JSON format preference
        """
        if as_json is not None:
            return as_json
        return self._config.json_format

    # ===== Factory Methods =====

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        api_url: str | None = None,
        cert_sha256: str | None = None,
        *,
        config: OutlineClientConfig | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AsyncOutlineClient, None]:
        """
        Create and initialize client (context manager).

        This is the preferred way to create a client as it ensures
        proper resource cleanup.

        Args:
            api_url: API URL (if not using config)
            cert_sha256: Certificate (if not using config)
            config: Pre-configured config object
            **kwargs: Additional options

        Yields:
            AsyncOutlineClient: Initialized and connected client

        Example:
            >>> async with AsyncOutlineClient.create(
            ...     api_url="https://server.com:12345/secret",
            ...     cert_sha256="abc123...",
            ...     timeout=60,
            ... ) as client:
            ...     server = await client.get_server_info()
            ...     print(f"Server: {server.name}")
        """
        if config is not None:
            client = cls(config, **kwargs)
        else:
            client = cls(api_url=api_url, cert_sha256=cert_sha256, **kwargs)

        async with client:
            yield client

    @classmethod
    def from_env(
        cls,
        env_file: Path | str | None = None,
        **overrides: Any,
    ) -> AsyncOutlineClient:
        """
        Create client from environment variables.

        Reads configuration from environment variables with OUTLINE_ prefix,
        or from a .env file.

        Args:
            env_file: Optional .env file path (default: .env)
            **overrides: Override specific configuration values

        Returns:
            AsyncOutlineClient: Configured client (not connected - use as context manager)

        Example:
            >>> # From default .env file
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     keys = await client.get_access_keys()
            >>>
            >>> # From custom file with overrides
            >>> async with AsyncOutlineClient.from_env(
            ...     env_file=".env.production",
            ...     timeout=60,
            ... ) as client:
            ...     server = await client.get_server_info()
        """
        config = OutlineClientConfig.from_env(env_file=env_file, **overrides)
        return cls(config)

    # ===== Utility Methods =====

    async def health_check(self) -> dict[str, Any]:
        """
        Perform basic health check.

        Tests connectivity by fetching server info.

        Returns:
            dict: Health status with healthy flag, connection state, and circuit state

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     health = await client.health_check()
            ...     if health["healthy"]:
            ...         print("✅ Service is healthy")
            ...     else:
            ...         print(f"❌ Service unhealthy: {health.get('error')}")
        """
        try:
            await self.get_server_info()
            return {
                "healthy": True,
                "connected": self.is_connected,
                "circuit_state": self.circuit_state,
            }
        except Exception as e:
            return {
                "healthy": False,
                "connected": self.is_connected,
                "error": str(e),
            }

    async def get_server_summary(self) -> dict[str, Any]:
        """
        Get comprehensive server overview.

        Collects server info, key count, and metrics (if enabled).

        Returns:
            dict: Server summary with all available information

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     summary = await client.get_server_summary()
            ...     print(f"Server: {summary['server']['name']}")
            ...     print(f"Keys: {summary['access_keys_count']}")
            ...     if "transfer_metrics" in summary:
            ...         total = summary["transfer_metrics"]["bytesTransferredByUserId"]
            ...         print(f"Total bytes: {sum(total.values())}")
        """
        summary: dict[str, Any] = {
            "healthy": True,
            "timestamp": __import__("time").time(),
        }

        try:
            # Server info (force JSON for summary)
            server = await self.get_server_info(as_json=True)
            summary["server"] = server

            # Access keys (force JSON)
            keys = await self.get_access_keys(as_json=True)
            summary["access_keys_count"] = len(keys.get("accessKeys", []))

            # Try metrics if enabled
            try:
                metrics_status = await self.get_metrics_status(as_json=True)
                if metrics_status.get("metricsEnabled"):
                    transfer = await self.get_transfer_metrics(as_json=True)
                    summary["transfer_metrics"] = transfer
            except Exception:
                pass

        except Exception as e:
            summary["healthy"] = False
            summary["error"] = str(e)

        return summary

    def __repr__(self) -> str:
        """
        String representation (safe for logging/debugging).

        Returns sanitized representation without exposing secrets.

        Returns:
            str: Safe string representation

        Example:
            >>> print(repr(client))
            AsyncOutlineClient(host=https://server.com:12345, status=connected)
        """
        status = "connected" if self.is_connected else "disconnected"
        cb = f", circuit={self.circuit_state}" if self.circuit_state else ""

        safe_url = Validators.sanitize_url_for_logging(self.api_url)

        return f"AsyncOutlineClient(host={safe_url}, status={status}{cb})"


# ===== Convenience Functions =====


def create_client(
    api_url: str,
    cert_sha256: str,
    **kwargs: Any,
) -> AsyncOutlineClient:
    """
    Create client with minimal parameters.

    Convenience function for quick client creation.

    Args:
        api_url: API URL with secret path
        cert_sha256: Certificate fingerprint
        **kwargs: Additional options (timeout, retry_attempts, etc.)

    Returns:
        AsyncOutlineClient: Client instance (use as context manager)

    Example:
        >>> client = create_client(
        ...     "https://server.com:12345/secret",
        ...     "abc123...",
        ...     timeout=60,
        ... )
        >>> async with client:
        ...     keys = await client.get_access_keys()
    """
    return AsyncOutlineClient(api_url=api_url, cert_sha256=cert_sha256, **kwargs)


__all__ = [
    "AsyncOutlineClient",
    "create_client",
]
