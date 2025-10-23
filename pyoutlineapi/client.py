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

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Final

from .api_mixins import AccessKeyMixin, DataLimitMixin, MetricsMixin, ServerMixin
from .audit import AuditLogger
from .base_client import BaseHTTPClient, MetricsCollector
from .common_types import Validators, build_config_overrides
from .config import OutlineClientConfig
from .exceptions import ConfigurationError, OutlineError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence
    from pathlib import Path

logger = logging.getLogger(__name__)

# Constants for multi-server management
_MAX_SERVERS: Final[int] = 50
_DEFAULT_SERVER_TIMEOUT: Final[float] = 5.0


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
            >>> async with AsyncOutlineClient.create(
            ...     api_url="https://server.com/path",
            ...     cert_sha256="abc123...",
            ...     timeout=20,
            ... ) as client:
            ...     info = await client.get_server_info()
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
            client = cls(config=config, audit_logger=audit_logger, metrics=metrics)
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
        *,
        env_file: str | Path | None = None,
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        **overrides: int | str | bool,
    ) -> AsyncOutlineClient:
        """Create client from environment variables.

        Modern approach using **overrides for configuration parameters.

        :param env_file: Path to environment file
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :param overrides: Configuration overrides (timeout, enable_logging, etc.)
        :return: Configured client instance
        :raises ConfigurationError: If environment configuration is invalid

        Example:
            >>> async with AsyncOutlineClient.from_env(
            ...     env_file=".env.production",
            ...     timeout=20,
            ... ) as client:
            ...     info = await client.get_server_info()
        """
        config = OutlineClientConfig.from_env(env_file=env_file, **overrides)
        return cls(config=config, audit_logger=audit_logger, metrics=metrics)

    # ===== Context Manager Methods =====
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        """Async context manager exit with comprehensive cleanup.

        Ensures graceful shutdown even on exceptions. Uses ordered cleanup
        sequence for proper resource deallocation.

        :param exc_type: Exception type if error occurred
        :param exc_val: Exception instance if error occurred
        :param exc_tb: Exception traceback
        :return: False to propagate exceptions
        """
        cleanup_errors: list[str] = []

        # Step 1: Graceful audit logger shutdown
        if self._audit_logger_instance is not None:
            try:
                if hasattr(self._audit_logger_instance, "shutdown"):
                    shutdown_method = self._audit_logger_instance.shutdown
                    if asyncio.iscoroutinefunction(shutdown_method):
                        await shutdown_method()
                    else:
                        shutdown_method()
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


# ===== Multi-Server Management =====


class MultiServerManager:
    """Manager for multiple Outline servers with unified configuration.

    Provides centralized management of multiple servers with consistent
    configurations, health monitoring, and automatic failover capabilities.

    Features:
    - Configuration-based server management
    - Individual server health tracking
    - Concurrent operations across servers
    - Automatic failover support
    - Unified metrics and audit logging

    Thread-safe: All operations use asyncio primitives.

    Usage:
        >>> configs = [
        ...     OutlineClientConfig.create_minimal("https://s1.com/path", "cert1..."),
        ...     OutlineClientConfig.create_minimal("https://s2.com/path", "cert2..."),
        ... ]
        >>> async with MultiServerManager(configs) as manager:
        ...     health = await manager.health_check_all()
        ...     result, server = await manager.execute_with_failover("get_server_info")
    """

    __slots__ = (
        "_audit_logger",
        "_clients",
        "_configs",
        "_default_timeout",
        "_lock",
        "_metrics",
    )

    def __init__(
        self,
        configs: Sequence[OutlineClientConfig],
        *,
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        default_timeout: float = _DEFAULT_SERVER_TIMEOUT,
    ) -> None:
        """Initialize multiserver manager.

        :param configs: Sequence of server configurations
        :param audit_logger: Shared audit logger for all servers
        :param metrics: Shared metrics collector for all servers
        :param default_timeout: Default timeout for operations
        :raises ConfigurationError: If configurations are invalid
        :raises ValueError: If too many servers provided
        """
        if not configs:
            raise ConfigurationError("At least one server configuration required")

        if len(configs) > _MAX_SERVERS:
            raise ValueError(f"Too many servers: {len(configs)} (max: {_MAX_SERVERS})")

        # Validate unique servers
        seen_urls: set[str] = set()
        for config in configs:
            normalized_url = config.api_url.lower().rstrip("/")
            if normalized_url in seen_urls:
                raise ConfigurationError(
                    f"Duplicate server URL: {Validators.sanitize_url_for_logging(config.api_url)}"
                )
            seen_urls.add(normalized_url)

        self._configs = list(configs)
        self._clients: dict[str, AsyncOutlineClient] = {}
        self._audit_logger = audit_logger
        self._metrics = metrics
        self._default_timeout = default_timeout
        self._lock = asyncio.Lock()

        _log_if_enabled(
            logging.INFO,
            f"MultiServerManager initialized with {len(configs)} server(s)",
        )

    @property
    def server_count(self) -> int:
        """Get number of configured servers.

        :return: Number of servers
        """
        return len(self._configs)

    @property
    def active_servers(self) -> int:
        """Get number of active (connected) servers.

        :return: Number of active servers
        """
        return sum(1 for client in self._clients.values() if client.is_connected)

    def get_server_names(self) -> list[str]:
        """Get list of sanitized server URLs.

        :return: List of safe server identifiers
        """
        return [
            Validators.sanitize_url_for_logging(config.api_url)
            for config in self._configs
        ]

    async def __aenter__(self) -> MultiServerManager:
        """Async context manager entry.

        Initializes all server connections using context managers.

        :return: Self reference
        :raises ConfigurationError: If no servers can be initialized
        """
        async with self._lock:
            errors: list[str] = []

            for idx, config in enumerate(self._configs):
                try:
                    # Create client using context manager
                    client = AsyncOutlineClient(
                        config=config,
                        audit_logger=self._audit_logger,
                        metrics=self._metrics,
                    )

                    # Initialize через context manager
                    await client.__aenter__()

                    # Use sanitized URL as key
                    server_id = Validators.sanitize_url_for_logging(config.api_url)
                    self._clients[server_id] = client

                    _log_if_enabled(
                        logging.INFO,
                        f"Server {idx + 1}/{len(self._configs)} initialized: {server_id}",
                    )

                except Exception as e:
                    safe_url = Validators.sanitize_url_for_logging(config.api_url)
                    error_msg = f"Failed to initialize server {safe_url}: {e}"
                    errors.append(error_msg)
                    _log_if_enabled(logging.WARNING, error_msg)

            if not self._clients:
                raise ConfigurationError(
                    f"Failed to initialize any servers. Errors: {'; '.join(errors)}"
                )

            _log_if_enabled(
                logging.INFO,
                f"MultiServerManager ready: {len(self._clients)}/{len(self._configs)} servers active",
            )

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        """Async context manager exit.

        Cleanly shuts down all clients using their context managers.

        :param exc_type: Exception type
        :param exc_val: Exception value
        :param exc_tb: Exception traceback
        :return: False to propagate exceptions
        """
        async with self._lock:
            errors: list[str] = []

            for server_id, client in self._clients.items():
                try:
                    # Shutdown через context manager
                    await client.__aexit__(None, None, None)
                    _log_if_enabled(logging.DEBUG, f"Server shutdown: {server_id}")
                except Exception as e:
                    error_msg = f"Shutdown error for {server_id}: {e}"
                    errors.append(error_msg)
                    _log_if_enabled(logging.WARNING, error_msg)

            self._clients.clear()

            if errors:
                _log_if_enabled(
                    logging.WARNING,
                    f"Shutdown completed with {len(errors)} error(s)",
                )

        return False

    def get_client(self, server_identifier: str | int) -> AsyncOutlineClient:
        """Get client by server identifier or index.

        :param server_identifier: Server URL (sanitized) or 0-based index
        :return: Client instance
        :raises KeyError: If server not found
        :raises IndexError: If index out of range
        """
        # Try as index first
        if isinstance(server_identifier, int):
            if 0 <= server_identifier < len(self._configs):
                config = self._configs[server_identifier]
                safe_url = Validators.sanitize_url_for_logging(config.api_url)
                return self._clients[safe_url]
            raise IndexError(
                f"Server index {server_identifier} out of range (0-{len(self._configs) - 1})"
            )

        # Try as server ID
        if server_identifier in self._clients:
            return self._clients[server_identifier]

        raise KeyError(f"Server not found: {server_identifier}")

    def get_all_clients(self) -> list[AsyncOutlineClient]:
        """Get all active clients.

        :return: List of client instances
        """
        return list(self._clients.values())

    async def health_check_all(
        self,
        timeout: float | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Perform health check on all servers.

        :param timeout: Timeout for each health check
        :return: Dictionary mapping server IDs to health check results
        """
        timeout = timeout or self._default_timeout
        results: dict[str, dict[str, Any]] = {}

        tasks = [
            self._health_check_single(server_id, client, timeout)
            for server_id, client in self._clients.items()
        ]

        completed_results = await asyncio.gather(*tasks, return_exceptions=True)

        for (server_id, _), result in zip(
            self._clients.items(), completed_results, strict=False
        ):
            if isinstance(result, Exception):
                results[server_id] = {
                    "healthy": False,
                    "error": str(result),
                    "error_type": type(result).__name__,
                }
            else:
                results[server_id] = result

        return results

    @staticmethod
    async def _health_check_single(
        server_id: str,
        client: AsyncOutlineClient,
        timeout: float,
    ) -> dict[str, Any]:
        """Perform health check on a single server.

        :param server_id: Server identifier
        :param client: Client instance
        :param timeout: Timeout for operation
        :return: Health check result
        """
        try:
            result = await asyncio.wait_for(
                client.health_check(),
                timeout=timeout,
            )
            result["server_id"] = server_id
            return result
        except asyncio.TimeoutError:
            return {
                "server_id": server_id,
                "healthy": False,
                "error": f"Health check timeout after {timeout}s",
                "error_type": "TimeoutError",
            }
        except Exception as e:
            return {
                "server_id": server_id,
                "healthy": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def get_healthy_servers(
        self,
        timeout: float | None = None,
    ) -> list[AsyncOutlineClient]:
        """Get list of healthy servers.

        :param timeout: Timeout for health checks
        :return: List of healthy clients
        """
        health_results = await self.health_check_all(timeout=timeout)

        healthy_clients: list[AsyncOutlineClient] = []
        for server_id, result in health_results.items():
            if result.get("healthy", False):
                try:
                    client = self.get_client(server_id)
                    healthy_clients.append(client)
                except (KeyError, IndexError):
                    continue

        return healthy_clients

    async def execute_on_all(
        self,
        operation: str,
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute operation on all servers concurrently.

        :param operation: Method name to execute
        :param args: Positional arguments for method
        :param timeout: Timeout for each operation
        :param kwargs: Keyword arguments for method
        :return: Dictionary mapping server IDs to results
        """
        timeout = timeout or self._default_timeout
        results: dict[str, Any] = {}

        tasks = [
            self._execute_single(server_id, client, operation, timeout, *args, **kwargs)
            for server_id, client in self._clients.items()
        ]

        completed_results = await asyncio.gather(*tasks, return_exceptions=True)

        for (server_id, _), result in zip(
            self._clients.items(), completed_results, strict=False
        ):
            results[server_id] = result

        return results

    @staticmethod
    async def _execute_single(
        server_id: str,
        client: AsyncOutlineClient,
        operation: str,
        timeout: float,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute operation on a single server.

        :param server_id: Server identifier
        :param client: Client instance
        :param operation: Method name
        :param timeout: Operation timeout
        :param args: Positional arguments
        :param kwargs: Keyword arguments
        :return: Operation result or exception
        """
        try:
            method = getattr(client, operation)
            result = await asyncio.wait_for(
                method(*args, **kwargs),
                timeout=timeout,
            )
            return {"success": True, "result": result}
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Operation timeout after {timeout}s",
                "error_type": "TimeoutError",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def execute_with_failover(
        self,
        operation: str,
        *args: Any,
        max_attempts: int | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> tuple[Any, str]:
        """Execute operation with automatic failover.

        Tries operation on servers in order until success or all fail.

        :param operation: Method name to execute
        :param args: Positional arguments
        :param max_attempts: Maximum servers to try (default: all)
        :param timeout: Timeout per attempt
        :param kwargs: Keyword arguments
        :return: Tuple of (result, server_id) on success
        :raises OutlineError: If all attempts fail
        """
        timeout = timeout or self._default_timeout
        max_attempts = max_attempts or len(self._clients)

        errors: list[str] = []
        attempted = 0

        for server_id, client in self._clients.items():
            if attempted >= max_attempts:
                break

            attempted += 1

            try:
                method = getattr(client, operation)
                result = await asyncio.wait_for(
                    method(*args, **kwargs),
                    timeout=timeout,
                )

                _log_if_enabled(
                    logging.INFO,
                    f"Operation '{operation}' succeeded on server {server_id} "
                    f"(attempt {attempted}/{max_attempts})",
                )

                return result, server_id

            except Exception as e:
                error_msg = f"{server_id}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                _log_if_enabled(
                    logging.WARNING,
                    f"Operation '{operation}' failed on {server_id} "
                    f"(attempt {attempted}/{max_attempts}): {e}",
                )

        # All attempts failed
        raise OutlineError(
            f"Operation '{operation}' failed on all {attempted} server(s)",
            details={"errors": errors, "attempted": attempted},
        )

    def get_status_summary(self) -> dict[str, Any]:
        """Get status summary for all servers.

        :return: Status summary dictionary
        """
        return {
            "total_servers": len(self._configs),
            "active_servers": self.active_servers,
            "server_statuses": {
                server_id: client.get_status()
                for server_id, client in self._clients.items()
            },
        }

    def __repr__(self) -> str:
        """String representation.

        :return: String representation
        """
        active = self.active_servers
        total = self.server_count
        return f"MultiServerManager(servers={active}/{total} active)"


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
    :return: Configured client instance (use with async context manager)
    :raises ConfigurationError: If parameters are invalid

    Example:
        >>> async with create_client(
        ...     api_url="https://server.com/path",
        ...     cert_sha256="abc123...",
        ...     timeout=20,
        ... ) as client:
        ...     info = await client.get_server_info()
    """
    return AsyncOutlineClient(
        api_url=api_url,
        cert_sha256=cert_sha256,
        audit_logger=audit_logger,
        metrics=metrics,
        **overrides,
    )


def create_multi_server_manager(
    configs: Sequence[OutlineClientConfig],
    *,
    audit_logger: AuditLogger | None = None,
    metrics: MetricsCollector | None = None,
    default_timeout: float = _DEFAULT_SERVER_TIMEOUT,
) -> MultiServerManager:
    """Create multiserver manager with configurations.

    Convenience function for creating a manager for multiple servers.

    :param configs: Sequence of server configurations
    :param audit_logger: Shared audit logger
    :param metrics: Shared metrics collector
    :param default_timeout: Default operation timeout
    :return: MultiServerManager instance (use with async context manager)
    :raises ConfigurationError: If configurations are invalid

    Example:
        >>> configs = [
        ...     OutlineClientConfig.create_minimal("https://s1.com/path", "cert1..."),
        ...     OutlineClientConfig.create_minimal("https://s2.com/path", "cert2..."),
        ... ]
        >>> async with create_multi_server_manager(configs) as manager:
        ...     health = await manager.health_check_all()
    """
    return MultiServerManager(
        configs=configs,
        audit_logger=audit_logger,
        metrics=metrics,
        default_timeout=default_timeout,
    )


__all__ = [
    "AsyncOutlineClient",
    "MultiServerManager",
    "create_client",
    "create_multi_server_manager",
]
