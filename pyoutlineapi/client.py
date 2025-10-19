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
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from .api_mixins import AccessKeyMixin, DataLimitMixin, MetricsMixin, ServerMixin
from .audit import AuditLogger
from .base_client import BaseHTTPClient, MetricsCollector
from .common_types import Validators, build_config_overrides
from .config import OutlineClientConfig
from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

logger = logging.getLogger(__name__)


def _log_if_enabled(level: int, message: str) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    """
    if logger.isEnabledFor(level):
        logger.log(level, message)


class AsyncOutlineClient(
    BaseHTTPClient,
    ServerMixin,
    AccessKeyMixin,
    DataLimitMixin,
    MetricsMixin,
):
    """Enhanced async client for Outline VPN Server API.

    Provides unified audit logging, metrics collection, correlation ID tracking,
    graceful shutdown, circuit breaker, rate limiting, and JSON format preference.

    Thread-safe: All operations are protected by underlying locks.
    Memory-optimized: Uses __slots__ to reduce memory footprint.
    """

    __slots__ = (
        "_audit_logger_instance",
        "_config",
        "_default_json_format",
    )

    def __init__(
        self,
        config: OutlineClientConfig | None = None,
        *,
        api_url: str | None = None,
        cert_sha256: str | None = None,
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        **overrides: int | str | bool,
    ) -> None:
        """Initialize Outline client.

        Modern approach using **overrides for configuration parameters.

        :param config: Client configuration object
        :param api_url: API URL (alternative to config)
        :param cert_sha256: Certificate fingerprint (alternative to config)
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :param overrides: Configuration overrides (timeout, retry_attempts, etc.)
        :raises ConfigurationError: If configuration is invalid

        Example:
            >>> client = AsyncOutlineClient(
            ...     api_url="https://server.com/path",
            ...     cert_sha256="abc123...",
            ...     timeout=20,
            ...     enable_logging=True
            ... )
        """
        # Build config_kwargs using utility function
        config_kwargs = build_config_overrides(**overrides)

        # Validate configuration using pattern matching
        resolved_config = self._resolve_configuration(
            config, api_url, cert_sha256, config_kwargs
        )

        self._config = resolved_config
        self._audit_logger_instance = audit_logger
        self._default_json_format = resolved_config.json_format

        # Initialize base HTTP client
        super().__init__(
            api_url=resolved_config.api_url,
            cert_sha256=resolved_config.cert_sha256,
            timeout=resolved_config.timeout,
            retry_attempts=resolved_config.retry_attempts,
            max_connections=resolved_config.max_connections,
            user_agent=resolved_config.user_agent,
            enable_logging=resolved_config.enable_logging,
            circuit_config=resolved_config.circuit_config,
            rate_limit=resolved_config.rate_limit,
            audit_logger=audit_logger,
            metrics=metrics,
        )

        if resolved_config.enable_logging:
            safe_url = Validators.sanitize_url_for_logging(self.api_url)
            _log_if_enabled(logging.INFO, f"Client initialized for {safe_url}")

    @staticmethod
    def _resolve_configuration(
        config: OutlineClientConfig | None,
        api_url: str | None,
        cert_sha256: str | None,
        kwargs: dict[str, Any],
    ) -> OutlineClientConfig:
        """Resolve and validate configuration from various input sources.

        :param config: Configuration object
        :param api_url: Direct API URL
        :param cert_sha256: Direct certificate
        :param kwargs: Additional kwargs
        :return: Resolved configuration
        :raises ConfigurationError: If configuration is invalid
        """
        match config, api_url, cert_sha256:
            # Direct parameters provided
            case None, str(url), str(cert) if url and cert:
                return OutlineClientConfig.create_minimal(url, cert, **kwargs)

            # Config object provided
            case OutlineClientConfig() as cfg, None, None:
                return cfg

            # Missing required parameters
            case None, None, _:
                raise ConfigurationError("Missing required 'api_url'")
            case None, _, None:
                raise ConfigurationError("Missing required 'cert_sha256'")
            case None, None, None:
                raise ConfigurationError(
                    "Either provide 'config' or both 'api_url' and 'cert_sha256'"
                )

            # Conflicting parameters
            case OutlineClientConfig(), str() | None, str() | None:
                raise ConfigurationError(
                    "Cannot specify both 'config' and direct parameters"
                )

            # Invalid combination
            case _:
                raise ConfigurationError("Invalid parameter combination")

    @property
    def config(self) -> OutlineClientConfig:
        """Get immutable copy of configuration.

        :return: Deep copy of configuration
        """
        return self._config.model_copy_immutable()

    def get_sanitized_config(self) -> dict[str, Any]:
        """Get configuration with sensitive data masked.

        :return: Sanitized configuration dictionary
        """
        return self._config.get_sanitized_config()

    @property
    def json_format(self) -> bool:
        """Get JSON format preference.

        :return: True if raw JSON format is preferred
        """
        return self._default_json_format

    # ===== Factory Methods =====

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        api_url: str | None = None,
        cert_sha256: str | None = None,
        *,
        config: OutlineClientConfig | None = None,
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        **overrides: int | str | bool,
    ) -> AsyncGenerator[AsyncOutlineClient, None]:
        """Create and initialize client (context manager).

        Automatically handles initialization and cleanup.
        Modern approach using **overrides for configuration.

        :param api_url: API URL
        :param cert_sha256: Certificate fingerprint
        :param config: Configuration object
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :param overrides: Configuration overrides (timeout, retry_attempts, etc.)
        :yield: Initialized client instance
        :raises ConfigurationError: If configuration is invalid
        """
        if config is not None:
            client = cls(config, audit_logger=audit_logger, metrics=metrics)
        else:
            client = cls(
                api_url=api_url,
                cert_sha256=cert_sha256,
                audit_logger=audit_logger,
                metrics=metrics,
                **overrides,
            )

        async with client:
            yield client

    @classmethod
    def from_env(
        cls,
        env_file: Path | str | None = None,
        *,
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        **overrides: int | str | bool,
    ) -> AsyncOutlineClient:
        """Create client from environment variables.

        Modern approach using **overrides for configuration.

        :param env_file: Path to .env file
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :param overrides: Configuration overrides (timeout, retry_attempts, etc.)
        :return: Configured client instance
        :raises ConfigurationError: If environment configuration is invalid

        Example:
            >>> client = AsyncOutlineClient.from_env(
            ...     env_file=".env.prod",
            ...     timeout=20,
            ...     enable_logging=True
            ... )
        """
        config = OutlineClientConfig.from_env(env_file=env_file, **overrides)
        return cls(config, audit_logger=audit_logger, metrics=metrics)

    # ===== Lifecycle Management =====

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        """Context manager exit with proper cleanup.

        Ensures audit logs are flushed before session closes.
        Uses defensive programming to handle cleanup errors gracefully.

        :param exc_type: Exception type
        :param exc_val: Exception value
        :param exc_tb: Exception traceback
        :return: False to propagate exceptions
        """
        cleanup_errors: list[str] = []

        # Step 1: Shutdown audit logger
        if self._audit_logger_instance and hasattr(
            self._audit_logger_instance, "shutdown"
        ):
            try:
                await self._audit_logger_instance.shutdown(timeout=5.0)
            except Exception as e:
                error_msg = f"Audit logger shutdown error: {e}"
                cleanup_errors.append(error_msg)
                _log_if_enabled(logging.WARNING, error_msg)

        # Step 2: Shutdown HTTP client
        try:
            await self.shutdown(timeout=30.0)
        except Exception as e:
            error_msg = f"HTTP client shutdown error: {e}"
            cleanup_errors.append(error_msg)
            _log_if_enabled(logging.ERROR, error_msg)

        # Step 3: Emergency cleanup if shutdown failed
        if cleanup_errors and hasattr(self, "_session"):
            try:
                if self._session and not self._session.closed:
                    await self._session.close()
                    _log_if_enabled(
                        logging.DEBUG,
                        "Emergency session cleanup completed",
                    )
            except Exception as e:
                _log_if_enabled(
                    logging.DEBUG,
                    f"Emergency cleanup error: {e}",
                )

        # Log summary of cleanup issues
        if cleanup_errors:
            _log_if_enabled(
                logging.WARNING,
                f"Cleanup completed with {len(cleanup_errors)} error(s): "
                f"{'; '.join(cleanup_errors)}",
            )

        # Always propagate the original exception
        return False

    # ===== Utility Methods =====

    async def health_check(self) -> dict[str, Any]:
        """Perform basic health check.

        Non-intrusive check that tests server connectivity without
        modifying any state.

        :return: Health check result dictionary
        """
        import time

        health_data: dict[str, Any] = {
            "timestamp": time.time(),
            "connected": self.is_connected,
            "circuit_state": self.circuit_state,
            "active_requests": self.active_requests,
            "rate_limit_available": self.available_slots,
        }

        try:
            # Non-modifying operation to test connectivity
            import asyncio

            start_time = asyncio.get_event_loop().time()
            await self.get_server_info()
            duration = asyncio.get_event_loop().time() - start_time

            health_data["healthy"] = True
            health_data["response_time_ms"] = round(duration * 1000, 2)

        except Exception as e:
            health_data["healthy"] = False
            health_data["error"] = str(e)
            health_data["error_type"] = type(e).__name__

        return health_data

    async def get_server_summary(self) -> dict[str, Any]:
        """Get comprehensive server overview.

        Aggregates multiple API calls into a single summary.
        Continues on partial failures to return maximum information.

        :return: Server summary dictionary
        """
        import time

        summary: dict[str, Any] = {
            "timestamp": time.time(),
            "healthy": True,
            "errors": [],
        }

        # Fetch server info
        try:
            server = await self.get_server_info(as_json=True)
            summary["server"] = server
        except Exception as e:
            summary["healthy"] = False
            summary["errors"].append(f"Server info error: {e}")
            _log_if_enabled(logging.DEBUG, f"Failed to fetch server info: {e}")

        # Fetch access keys count
        try:
            keys = await self.get_access_keys(as_json=True)
            summary["access_keys_count"] = len(keys.get("accessKeys", []))
        except Exception as e:
            summary["healthy"] = False
            summary["errors"].append(f"Access keys error: {e}")
            _log_if_enabled(logging.DEBUG, f"Failed to fetch access keys: {e}")

        # Fetch metrics if enabled
        try:
            metrics_status = await self.get_metrics_status(as_json=True)
            summary["metrics_enabled"] = metrics_status.get("metricsEnabled", False)

            if metrics_status.get("metricsEnabled"):
                try:
                    transfer = await self.get_transfer_metrics(as_json=True)
                    summary["transfer_metrics"] = transfer
                except Exception as e:
                    summary["errors"].append(f"Transfer metrics error: {e}")
                    _log_if_enabled(
                        logging.DEBUG,
                        f"Failed to fetch transfer metrics: {e}",
                    )

        except Exception as e:
            summary["errors"].append(f"Metrics status error: {e}")
            _log_if_enabled(logging.DEBUG, f"Failed to fetch metrics status: {e}")

        # Add client status
        summary["client_status"] = {
            "connected": self.is_connected,
            "circuit_state": self.circuit_state,
            "active_requests": self.active_requests,
            "rate_limit": {
                "limit": self.rate_limit,
                "available": self.available_slots,
            },
        }

        return summary

    def get_status(self) -> dict[str, Any]:
        """Get current client status (synchronous).

        Returns immediate status without making API calls.

        :return: Status dictionary
        """
        return {
            "connected": self.is_connected,
            "circuit_state": self.circuit_state,
            "active_requests": self.active_requests,
            "rate_limit": {
                "limit": self.rate_limit,
                "available": self.available_slots,
                "active": self.active_requests,
            },
            "circuit_metrics": self.get_circuit_metrics(),
        }

    def __repr__(self) -> str:
        """Safe string representation without secrets.

        :return: String representation
        """
        status = "connected" if self.is_connected else "disconnected"
        parts = [f"status={status}"]

        if self.circuit_state:
            parts.append(f"circuit={self.circuit_state}")

        if self.active_requests > 0:
            parts.append(f"active={self.active_requests}")

        safe_url = Validators.sanitize_url_for_logging(self.api_url)
        status_str = ", ".join(parts)

        return f"AsyncOutlineClient(host={safe_url}, {status_str})"

    def __str__(self) -> str:
        """User-friendly string representation.

        :return: String representation
        """
        safe_url = Validators.sanitize_url_for_logging(self.api_url)
        status = "connected" if self.is_connected else "disconnected"
        return f"OutlineClient({safe_url}) - {status}"


# ===== Convenience Functions =====


def create_client(
    api_url: str,
    cert_sha256: str,
    *,
    audit_logger: AuditLogger | None = None,
    metrics: MetricsCollector | None = None,
    **overrides: int | str | bool,
) -> AsyncOutlineClient:
    """Create client with minimal parameters.

    Convenience function for quick client creation without
    explicit configuration object. Uses modern **overrides approach.

    :param api_url: API URL with secret path
    :param cert_sha256: SHA-256 certificate fingerprint
    :param audit_logger: Custom audit logger (optional)
    :param metrics: Custom metrics collector (optional)
    :param overrides: Configuration overrides (timeout, retry_attempts, etc.)
    :return: Configured client instance
    :raises ConfigurationError: If parameters are invalid

    Example:
        >>> client = create_client(
        ...     api_url="https://server.com/path",
        ...     cert_sha256="abc123...",
        ...     timeout=20,
        ...     enable_logging=True,
        ...     rate_limit=50
        ... )
    """
    return AsyncOutlineClient(
        api_url=api_url,
        cert_sha256=cert_sha256,
        audit_logger=audit_logger,
        metrics=metrics,
        **overrides,
    )


__all__ = [
    "AsyncOutlineClient",
    "create_client",
]
