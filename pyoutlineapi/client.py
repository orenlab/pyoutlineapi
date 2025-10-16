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
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from .api_mixins import AccessKeyMixin, DataLimitMixin, MetricsMixin, ServerMixin
from .audit import AuditLogger
from .base_client import BaseHTTPClient, MetricsCollector
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
    """Enhanced async client for Outline VPN Server API.

    ENTERPRISE FEATURES:
    - Unified audit logging (sync and async)
    - Metrics collection
    - Correlation ID tracking
    - Graceful shutdown
    - Circuit breaker
    - Rate limiting
    - JSON format preference
    """

    def __init__(
        self,
        config: OutlineClientConfig | None = None,
        *,
        api_url: str | None = None,
        cert_sha256: str | None = None,
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Outline client with enterprise features."""
        # Handle configuration with pattern matching
        match config, api_url, cert_sha256:
            case None, str(url), str(cert) if url and cert:
                config = OutlineClientConfig.create_minimal(url, cert, **kwargs)

            case OutlineClientConfig() as cfg, None, None:
                config = cfg

            case None, None, _:
                raise ConfigurationError("Missing required 'api_url'")
            case None, _, None:
                raise ConfigurationError("Missing required 'cert_sha256'")
            case None, None, None:
                raise ConfigurationError(
                    "Either provide 'config' or both 'api_url' and 'cert_sha256'"
                )

            case OutlineClientConfig(), str() | None, str() | None:
                raise ConfigurationError(
                    "Cannot specify both 'config' and direct parameters"
                )

            case _:
                raise ConfigurationError("Invalid parameter combination")

        self._config = config

        # Store audit logger instance for mixins
        self._audit_logger_instance = audit_logger

        # Store JSON format preference for mixins
        self._default_json_format = config.json_format

        super().__init__(
            api_url=config.api_url,
            cert_sha256=config.cert_sha256,
            timeout=config.timeout,
            retry_attempts=config.retry_attempts,
            max_connections=config.max_connections,
            enable_logging=config.enable_logging,
            circuit_config=config.circuit_config,
            rate_limit=config.rate_limit,
            audit_logger=audit_logger,
            metrics=metrics,
        )

        if config.enable_logging:
            safe_url = Validators.sanitize_url_for_logging(self.api_url)
            logger.info(f"Client initialized for {safe_url}")

    @property
    def config(self) -> OutlineClientConfig:
        """Get IMMUTABLE copy of configuration.

        Returns a deep copy to prevent accidental mutation.
        Safe for display and inspection.
        """
        return self._config.model_copy_immutable()

    def get_sanitized_config(self) -> dict[str, Any]:
        """Get configuration with sensitive data masked."""
        return self._config.get_sanitized_config()

    @property
    def json_format(self) -> bool:
        """Get JSON format preference."""
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
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AsyncOutlineClient, None]:
        """Create and initialize client (context manager)."""
        if config is not None:
            client = cls(config, audit_logger=audit_logger, metrics=metrics, **kwargs)
        else:
            client = cls(
                api_url=api_url,
                cert_sha256=cert_sha256,
                audit_logger=audit_logger,
                metrics=metrics,
                **kwargs,
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
        **overrides: Any,
    ) -> AsyncOutlineClient:
        """Create client from environment variables."""
        config = OutlineClientConfig.from_env(env_file=env_file, **overrides)
        return cls(config, audit_logger=audit_logger, metrics=metrics)

    # ===== Lifecycle Management =====

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with proper cleanup.

        Handles cleanup in the correct order:
        1. Shutdown audit logger (if supported)
        2. Call parent shutdown (which closes HTTP session)

        This ensures all audit logs are flushed before session closes.
        """
        try:
            # Step 1: Shutdown audit logger if it supports async shutdown
            if self._audit_logger_instance and hasattr(
                self._audit_logger_instance, "shutdown"
            ):
                try:
                    await self._audit_logger_instance.shutdown()
                except Exception as e:
                    logger.warning(f"Error during audit logger shutdown: {e}")

            # Step 2: Call parent shutdown (closes session, waits for active requests)
            await self.shutdown()

            return False

        except Exception as e:
            logger.error(f"Error during __aexit__: {e}", exc_info=True)

            # Last resort: try to close session
            try:
                if (
                    hasattr(self, "_session")
                    and self._session
                    and not self._session.closed
                ):
                    await self._session.close()
            except Exception:
                pass

            raise

    # ===== Utility Methods =====

    async def health_check(self) -> dict[str, Any]:
        """Perform basic health check."""
        try:
            await self.get_server_info()
            return {
                "healthy": True,
                "connected": self.is_connected,
                "circuit_state": self.circuit_state,
                "active_requests": self.active_requests,
            }
        except Exception as e:
            return {
                "healthy": False,
                "connected": self.is_connected,
                "error": str(e),
                "active_requests": self.active_requests,
            }

    async def get_server_summary(self) -> dict[str, Any]:
        """Get comprehensive server overview."""
        summary: dict[str, Any] = {
            "healthy": True,
            "timestamp": time.time(),
        }

        try:
            # Server info (force JSON)
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
        """Safe string representation without secrets."""
        status = "connected" if self.is_connected else "disconnected"
        cb = f", circuit={self.circuit_state}" if self.circuit_state else ""

        safe_url = Validators.sanitize_url_for_logging(self.api_url)

        return f"AsyncOutlineClient(host={safe_url}, status={status}{cb})"


# ===== Convenience Functions =====


def create_client(
    api_url: str,
    cert_sha256: str,
    *,
    audit_logger: AuditLogger | None = None,
    metrics: MetricsCollector | None = None,
    **kwargs: Any,
) -> AsyncOutlineClient:
    """Create client with minimal parameters."""
    return AsyncOutlineClient(
        api_url=api_url,
        cert_sha256=cert_sha256,
        audit_logger=audit_logger,
        metrics=metrics,
        **kwargs,
    )


__all__ = [
    "AsyncOutlineClient",
    "create_client",
]
