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
from weakref import WeakValueDictionary

from .api_mixins import AccessKeyMixin, DataLimitMixin, MetricsMixin, ServerMixin
from .audit import AuditLogger
from .base_client import BaseHTTPClient, MetricsCollector
from .common_types import ConfigOverrides, Validators, build_config_overrides
from .config import OutlineClientConfig
from .exceptions import ConfigurationError
from .models import AccessKeyList, MetricsStatusResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence
    from pathlib import Path

    from typing_extensions import Unpack

logger = logging.getLogger(__name__)

# Constants for multi-server management
_MAX_SERVERS: Final[int] = 50
_DEFAULT_SERVER_TIMEOUT: Final[float] = 5.0

_client_cache: WeakValueDictionary[int, AsyncOutlineClient] = WeakValueDictionary()


class AsyncOutlineClient(
    BaseHTTPClient,
    ServerMixin,
    AccessKeyMixin,
    DataLimitMixin,
    MetricsMixin,
):
    """High-performance async client for Outline VPN Server API."""

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
        **overrides: Unpack[ConfigOverrides],
    ) -> None:
        """Initialize Outline client with modern configuration approach.

        Uses structural pattern matching for configuration resolution.

        :param config: Client configuration object
        :param api_url: API URL (alternative to config)
        :param cert_sha256: Certificate fingerprint (alternative to config)
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :param overrides: Configuration overrides (timeout, retry_attempts, etc.)
        :raises ConfigurationError: If configuration is invalid

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     info = await client.get_server_info()
        """
        # Build config_kwargs using utility function (DRY)
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
            allow_private_networks=resolved_config.allow_private_networks,
            resolve_dns_for_ssrf=resolved_config.resolve_dns_for_ssrf,
            audit_logger=audit_logger,
            metrics=metrics,
        )

        # Cache instance for weak reference tracking (automatic cleanup)
        _client_cache[id(self)] = self

        if resolved_config.enable_logging and logger.isEnabledFor(logging.INFO):
            safe_url = Validators.sanitize_url_for_logging(self.api_url)
            logger.info("Client initialized for %s", safe_url)

    @staticmethod
    def _resolve_configuration(
        config: OutlineClientConfig | None,
        api_url: str | None,
        cert_sha256: str | None,
        kwargs: dict[str, Any],
    ) -> OutlineClientConfig:
        """Resolve and validate configuration using pattern matching.

        :param config: Configuration object
        :param api_url: Direct API URL
        :param cert_sha256: Direct certificate
        :param kwargs: Additional kwargs
        :return: Resolved configuration
        :raises ConfigurationError: If configuration is invalid
        """
        match config, api_url, cert_sha256:
            # Pattern 1: Direct parameters provided (most common case)
            case None, str(url), str(cert) if url and cert:
                return OutlineClientConfig.create_minimal(url, cert, **kwargs)

            # Pattern 2: Config object provided
            case OutlineClientConfig() as cfg, None, None:
                return cfg

            # Pattern 3: Missing required parameters
            case None, None, _:
                raise ConfigurationError(
                    "Missing required 'api_url'",
                    field="api_url",
                    security_issue=False,
                )
            case None, _, None:
                raise ConfigurationError(
                    "Missing required 'cert_sha256'",
                    field="cert_sha256",
                    security_issue=True,
                )

            # Pattern 4: Conflicting parameters
            case OutlineClientConfig(), str() | None, str() | None:
                raise ConfigurationError(
                    "Cannot specify both 'config' and direct parameters"
                )

            # Pattern 5: Invalid combination (catch-all)
            case _:
                raise ConfigurationError("Invalid parameter combination")

    @property
    def config(self) -> OutlineClientConfig:
        """Get immutable copy of configuration.

        :return: Deep copy of configuration
        """
        return self._config.model_copy_immutable()

    @property
    def get_sanitized_config(self) -> dict[str, Any]:
        """Delegate to config's sanitized representation.

        See: OutlineClientConfig.get_sanitized_config().

        :return: Sanitized configuration from underlying config object
        """
        return self._config.get_sanitized_config

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
        **overrides: Unpack[ConfigOverrides],
    ) -> AsyncGenerator[AsyncOutlineClient, None]:
        """Create and initialize client as async context manager.

        Automatically handles initialization and cleanup.
        Recommended way to create clients in async contexts.

        :param api_url: API URL
        :param cert_sha256: Certificate fingerprint
        :param config: Configuration object
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :param overrides: Configuration overrides (timeout, retry_attempts, etc.)
        :yield: Initialized client instance
        :raises ConfigurationError: If configuration is invalid

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     keys = await client.get_access_keys()
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
        **overrides: Unpack[ConfigOverrides],
    ) -> AsyncOutlineClient:
        """Create client from environment variables.

        Reads configuration from environment or .env file.
        Modern approach using **overrides for runtime configuration.

        :param env_file: Path to environment file (.env)
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
    ) -> None:
        """Async context manager exit with comprehensive cleanup.

        Ensures graceful shutdown even on exceptions. Uses ordered cleanup
        sequence for proper resource deallocation.

        Cleanup order:
        1. Audit logger shutdown (drain queue)
        2. HTTP client shutdown (close connections)
        3. Emergency cleanup if steps 1-2 failed

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
            except Exception as e:
                error_msg = f"Audit logger shutdown error: {e}"
                cleanup_errors.append(error_msg)
                if logger.isEnabledFor(logging.WARNING):
                    logger.warning(error_msg)

        # Step 2: Shutdown HTTP client
        try:
            await self.shutdown(timeout=30.0)
        except Exception as e:
            error_msg = f"HTTP client shutdown error: {e}"
            cleanup_errors.append(error_msg)
            if logger.isEnabledFor(logging.ERROR):
                logger.error(error_msg)

        # Step 3: Emergency cleanup if shutdown failed
        if cleanup_errors and hasattr(self, "_session"):
            try:
                if self._session and not self._session.closed:
                    await self._session.close()
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Emergency session cleanup completed")
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Emergency cleanup error: %s", e)

        # Log summary of cleanup issues
        if cleanup_errors and logger.isEnabledFor(logging.WARNING):
            logger.warning(
                "Cleanup completed with %d error(s): %s",
                len(cleanup_errors),
                "; ".join(cleanup_errors),
            )

        # Always propagate the original exception
        return None

    # ===== Utility Methods =====

    async def health_check(self) -> dict[str, Any]:
        """Perform basic health check.

        Non-intrusive check that tests server connectivity without
        modifying any state. Returns comprehensive health metrics.

        :return: Health check result dictionary with response time

        Example result:
            {
                "timestamp": 1234567890.123,
                "healthy": True,
                "response_time_ms": 45.2,
                "connected": True,
                "circuit_state": "closed",
                "active_requests": 2,
                "rate_limit_available": 98
            }
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
            start_time = time.monotonic()
            await self.get_server_info()
            duration = time.monotonic() - start_time

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
        Executes non-dependent calls concurrently for performance.

        :return: Server summary dictionary with aggregated data

        Example result:
            {
                "timestamp": 1234567890.123,
                "healthy": True,
                "server": {...},
                "access_keys_count": 10,
                "metrics_enabled": True,
                "transfer_metrics": {...},
                "client_status": {...},
                "errors": []
            }
        """
        import time

        summary: dict[str, Any] = {
            "timestamp": time.time(),
            "healthy": True,
            "errors": [],
        }

        server_task = self.get_server_info(as_json=True)
        keys_task = self.get_access_keys(as_json=True)
        metrics_status_task = self.get_metrics_status(as_json=True)

        server_result, keys_result, metrics_status_result = await asyncio.gather(
            server_task, keys_task, metrics_status_task, return_exceptions=True
        )

        # Process server info
        if isinstance(server_result, Exception):
            summary["healthy"] = False
            summary["errors"].append(f"Server info error: {server_result}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Failed to fetch server info: %s", server_result)
        else:
            summary["server"] = server_result

        # Process access keys
        if isinstance(keys_result, Exception):
            summary["healthy"] = False
            summary["errors"].append(f"Access keys error: {keys_result}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Failed to fetch access keys: %s", keys_result)
        elif isinstance(keys_result, dict):
            keys_list = keys_result.get("accessKeys", [])
            summary["access_keys_count"] = (
                len(keys_list) if isinstance(keys_list, list) else 0
            )
        elif isinstance(keys_result, AccessKeyList):
            summary["access_keys_count"] = len(keys_result.access_keys)
        else:
            summary["access_keys_count"] = 0

        # Process metrics status
        if isinstance(metrics_status_result, Exception):
            summary["errors"].append(f"Metrics status error: {metrics_status_result}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Failed to fetch metrics status: %s", metrics_status_result
                )
        elif isinstance(metrics_status_result, dict):
            metrics_enabled = bool(metrics_status_result.get("metricsEnabled", False))
            summary["metrics_enabled"] = metrics_enabled

            # Fetch transfer metrics if enabled (dependent call - sequential)
            if metrics_enabled:
                try:
                    transfer = await self.get_transfer_metrics(as_json=True)
                    summary["transfer_metrics"] = transfer
                except Exception as e:
                    summary["errors"].append(f"Transfer metrics error: {e}")
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Failed to fetch transfer metrics: %s", e)
        elif isinstance(metrics_status_result, MetricsStatusResponse):
            summary["metrics_enabled"] = metrics_status_result.metrics_enabled
            if metrics_status_result.metrics_enabled:
                try:
                    transfer = await self.get_transfer_metrics(as_json=True)
                    summary["transfer_metrics"] = transfer
                except Exception as e:
                    summary["errors"].append(f"Transfer metrics error: {e}")
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Failed to fetch transfer metrics: %s", e)
        else:
            summary["metrics_enabled"] = False

        # Add client status (synchronous, no API call)
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
        Useful for monitoring and debugging.

        :return: Status dictionary with all client metrics

        Example result:
            {
                "connected": True,
                "circuit_state": "closed",
                "active_requests": 2,
                "rate_limit": {
                    "limit": 100,
                    "available": 98,
                    "active": 2
                },
                "circuit_metrics": {...}
            }
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

        Does not expose any sensitive information (URLs, certificates, tokens).

        :return: String representation
        """
        status = "connected" if self.is_connected else "disconnected"
        parts = [f"status={status}"]

        if self.circuit_state:
            parts.append(f"circuit={self.circuit_state}")

        if self.active_requests:
            parts.append(f"requests={self.active_requests}")

        return f"AsyncOutlineClient({', '.join(parts)})"


# ===== Multi-Server Manager =====


class MultiServerManager:
    """High-performance manager for multiple Outline servers.

    Features:
    - Concurrent operations across all servers
    - Health checking and automatic failover
    - Aggregated metrics and status
    - Graceful shutdown with cleanup
    - Thread-safe operations

    Limits:
    - Maximum 50 servers (configurable via _MAX_SERVERS)
    - Automatic cleanup with weak references
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
        :param default_timeout: Default timeout for operations (seconds)
        :raises ConfigurationError: If too many servers or invalid configs
        """
        if len(configs) > _MAX_SERVERS:
            raise ConfigurationError(
                f"Too many servers: {len(configs)} (max: {_MAX_SERVERS})"
            )

        if not configs:
            raise ConfigurationError("At least one server configuration required")

        self._configs = list(configs)
        self._clients: dict[str, AsyncOutlineClient] = {}
        self._audit_logger = audit_logger
        self._metrics = metrics
        self._default_timeout = default_timeout
        self._lock = asyncio.Lock()

    @property
    def server_count(self) -> int:
        """Get total number of configured servers.

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

        URLs are sanitized to remove sensitive path information.

        :return: List of safe server identifiers
        """
        return [
            Validators.sanitize_url_for_logging(config.api_url)
            for config in self._configs
        ]

    async def __aenter__(self) -> MultiServerManager:
        """Async context manager entry.

        :return: Self reference
        :raises ConfigurationError: If NO servers can be initialized
        """
        async with self._lock:
            # Create initialization tasks for concurrent execution
            init_tasks = []
            for config in self._configs:
                client = AsyncOutlineClient(
                    config=config,
                    audit_logger=self._audit_logger,
                    metrics=self._metrics,
                )
                init_tasks.append((config, client.__aenter__()))

            results = await asyncio.gather(
                *[task for _, task in init_tasks],
                return_exceptions=True,
            )

            # Process results
            errors: list[str] = []
            for idx, ((config, _), result) in enumerate(
                zip(init_tasks, results, strict=True)
            ):
                safe_url = Validators.sanitize_url_for_logging(config.api_url)

                if isinstance(result, Exception):
                    error_msg = f"Failed to initialize server {safe_url}: {result}"
                    errors.append(error_msg)
                    if logger.isEnabledFor(logging.WARNING):
                        logger.warning(error_msg)
                else:
                    # Get the client that was initialized
                    client = AsyncOutlineClient(
                        config=config,
                        audit_logger=self._audit_logger,
                        metrics=self._metrics,
                    )
                    self._clients[safe_url] = client

                    if logger.isEnabledFor(logging.INFO):
                        logger.info(
                            "Server %d/%d initialized: %s",
                            idx + 1,
                            len(self._configs),
                            safe_url,
                        )

            if not self._clients:
                raise ConfigurationError(
                    f"Failed to initialize any servers. Errors: {'; '.join(errors)}"
                )

            if logger.isEnabledFor(logging.INFO):
                logger.info(
                    "MultiServerManager ready: %d/%d servers active",
                    len(self._clients),
                    len(self._configs),
                )

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        """Async context manager exit.

        :param exc_type: Exception type
        :param exc_val: Exception value
        :param exc_tb: Exception traceback
        :return: False to propagate exceptions
        """
        async with self._lock:
            shutdown_tasks = [
                client.__aexit__(None, None, None) for client in self._clients.values()
            ]

            results = await asyncio.gather(*shutdown_tasks, return_exceptions=True)

            errors = [
                f"{server_id}: {result}"
                for (server_id, _), result in zip(
                    self._clients.items(), results, strict=False
                )
                if isinstance(result, Exception)
            ]

            self._clients.clear()

            if errors and logger.isEnabledFor(logging.WARNING):
                logger.warning("Shutdown completed with %d error(s)", len(errors))

        return False

    def get_client(self, server_identifier: str | int) -> AsyncOutlineClient:
        """Get client by server identifier or index.

        :param server_identifier: Server URL (sanitized) or 0-based index
        :return: Client instance
        :raises KeyError: If server not found
        :raises IndexError: If index out of range
        """
        # Try as index first (fast path for common case)
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
        """Perform health check on all servers concurrently.

        :param timeout: Timeout for each health check
        :return: Dictionary mapping server IDs to health check results
        """
        timeout = timeout or self._default_timeout

        tasks = [
            self._health_check_single(server_id, client, timeout)
            for server_id, client in self._clients.items()
        ]

        # Execute concurrently
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dictionary
        results: dict[str, dict[str, Any]] = {}
        for (server_id, _), result in zip(
            self._clients.items(), results_list, strict=False
        ):
            if isinstance(result, BaseException):
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
        """Perform health check on a single server with timeout.

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
        """Get list of healthy servers after health check.

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

    def get_status_summary(self) -> dict[str, Any]:
        """Get aggregated status summary for all servers.

        Synchronous operation - no API calls made.

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
    **overrides: Unpack[ConfigOverrides],
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

    Example (advanced, prefer from_env for production):
        >>> async with AsyncOutlineClient.from_env() as client:
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
        ...     OutlineClientConfig.create_minimal("https://s1.com/path", "a" * 64),
        ...     OutlineClientConfig.create_minimal("https://s2.com/path", "b" * 64),
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
