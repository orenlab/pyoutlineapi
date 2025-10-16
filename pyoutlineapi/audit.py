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
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, Protocol, TypeVar, cast

from .common_types import DEFAULT_SENSITIVE_KEYS

logger = logging.getLogger(__name__)

# Type variables
F = TypeVar("F", bound=Callable[..., Any])


# ===== Audit Logger Protocol =====


class AuditLogger(Protocol):
    """Protocol for audit logging implementations.

    Supports both sync and async logging for maximum flexibility.
    """

    def log_action(
            self,
            action: str,
            resource: str,
            *,
            user: str | None = None,
            details: dict[str, Any] | None = None,
            correlation_id: str | None = None,
    ) -> None:
        """Log auditable action (synchronous)."""
        ...

    async def alog_action(
            self,
            action: str,
            resource: str,
            *,
            user: str | None = None,
            details: dict[str, Any] | None = None,
            correlation_id: str | None = None,
    ) -> None:
        """Log auditable action (asynchronous)."""
        ...


# ===== Default Implementation =====


class DefaultAuditLogger:
    """Production-ready audit logger with async queue processing.

    Features:
    - Non-blocking async logging via queue
    - Backwards-compatible sync logging
    - Automatic queue management
    - Graceful shutdown support
    - Sensitive data filtering
    - Structured logging with extra fields for formatters
    """

    def __init__(self, *, enable_async: bool = True, queue_size: int = 1000):
        """Initialize audit logger.

        Args:
            enable_async: Enable async logging queue (recommended for production)
            queue_size: Maximum size of async logging queue
        """
        self._enable_async = enable_async
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._task: asyncio.Task | None = None
        self._queue_size = queue_size
        self._shutdown = False

    def log_action(
            self,
            action: str,
            resource: str,
            *,
            user: str | None = None,
            details: dict[str, Any] | None = None,
            correlation_id: str | None = None,
    ) -> None:
        """Log auditable action (synchronous).

        For backwards compatibility and simple use cases.
        """
        extra = self._prepare_extra(action, resource, user, details, correlation_id)

        # Format message for readability
        user_str = f" by {user}" if user else ""
        corr_str = f" [{correlation_id}]" if correlation_id else ""
        details_str = f" | {details}" if details else ""

        # Log with extra fields that formatter can use
        logger.info(
            f"[AUDIT] {action} on {resource}{user_str}{corr_str}{details_str}",
            extra=extra,
        )

    async def alog_action(
            self,
            action: str,
            resource: str,
            *,
            user: str | None = None,
            details: dict[str, Any] | None = None,
            correlation_id: str | None = None,
    ) -> None:
        """Log auditable action (asynchronous, non-blocking).

        Uses queue-based processing to avoid blocking operations.
        Falls back to sync logging if async is disabled or queue is full.
        """
        if not self._enable_async:
            self.log_action(
                action,
                resource,
                user=user,
                details=details,
                correlation_id=correlation_id,
            )
            return

        # Lazy queue initialization
        if self._queue is None and not self._shutdown:
            self._queue = asyncio.Queue(maxsize=self._queue_size)
            self._task = asyncio.create_task(self._process_queue())

        extra = self._prepare_extra(action, resource, user, details, correlation_id)

        # Try to add to queue, fall back to sync if full
        try:
            if self._queue and not self._shutdown:
                self._queue.put_nowait(extra)
            else:
                self.log_action(
                    action,
                    resource,
                    user=user,
                    details=details,
                    correlation_id=correlation_id,
                )
        except asyncio.QueueFull:
            logger.warning("[AUDIT] Queue full, falling back to sync logging")
            self.log_action(
                action,
                resource,
                user=user,
                details=details,
                correlation_id=correlation_id,
            )

    async def _process_queue(self) -> None:
        """Background task to process audit log queue.

        Runs continuously until shutdown signal is received.
        Handles exceptions to prevent task from crashing.
        """
        try:
            while not self._shutdown:
                try:
                    # Wait for item with timeout to check shutdown flag
                    extra = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                    # Extract fields for message
                    action = extra.get("action", "unknown")
                    resource = extra.get("resource", "unknown")
                    user = extra.get("user")
                    correlation_id = extra.get("correlation_id")
                    details = extra.get("details")

                    # Format message
                    user_str = f" by {user}" if user else ""
                    corr_str = f" [{correlation_id}]" if correlation_id else ""
                    details_str = f" | {details}" if details else ""

                    # Log with extra fields
                    logger.info(
                        f"[AUDIT] {action} on {resource}{user_str}{corr_str}{details_str}",
                        extra=extra,
                    )

                    self._queue.task_done()

                except asyncio.TimeoutError:
                    # Normal timeout, continue loop to check shutdown
                    continue
                except Exception as e:
                    logger.error(f"[AUDIT] Error processing queue: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.debug("[AUDIT] Queue processing cancelled")
            raise
        finally:
            logger.debug("[AUDIT] Queue processing stopped")

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        """Gracefully shutdown audit logger.

        Args:
            timeout: Maximum time to wait for queue to drain (seconds)
        """
        if self._shutdown:
            return

        self._shutdown = True
        logger.debug("[AUDIT] Shutting down audit logger")

        # Wait for queue to drain
        if self._queue is not None:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    f"[AUDIT] Queue did not drain within {timeout}s, "
                    f"{self._queue.qsize()} items remaining"
                )

        # Cancel background task
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.debug("[AUDIT] Audit logger shutdown complete")

    @staticmethod
    def _prepare_extra(
            action: str,
            resource: str,
            user: str | None,
            details: dict[str, Any] | None,
            correlation_id: str | None,
    ) -> dict[str, Any]:
        """Prepare structured logging context with sanitization."""
        extra = {
            "action": action,
            "resource": resource,
            "timestamp": time.time(),
            "is_audit": True,  # Flag for formatter
        }

        if user is not None:
            extra["user"] = user
        if correlation_id is not None:
            extra["correlation_id"] = correlation_id
        if details is not None:
            # Sanitize sensitive data
            extra["details"] = AuditDecorator.sanitize_details(details)

        return extra


# ===== No-Op Implementation =====


class NoOpAuditLogger:
    """No-op audit logger for when auditing is disabled."""

    def log_action(
            self,
            action: str,
            resource: str,
            *,
            user: str | None = None,
            details: dict[str, Any] | None = None,
            correlation_id: str | None = None,
    ) -> None:
        """Do nothing."""

    async def alog_action(
            self,
            action: str,
            resource: str,
            *,
            user: str | None = None,
            details: dict[str, Any] | None = None,
            correlation_id: str | None = None,
    ) -> None:
        """Do nothing."""

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        """Do nothing."""


# ===== Audit Decorator =====


class AuditDecorator:
    """Universal audit logging decorator for both mixins and HTTP client.

    Features:
    - Works with both sync and async functions
    - Configurable resource extraction strategies
    - Automatic sensitive data filtering
    - Zero code duplication (DRY principle)
    - Exception-safe execution
    """

    @staticmethod
    def audit_action(
            action: str,
            *,
            resource_from: str | Callable | None = None,
            log_success: bool = True,
            log_failure: bool = True,
            extract_details: Callable | None = None,
    ) -> Callable[[F], F]:
        """Decorator for automatic audit logging.

        Args:
            action: Action being performed (e.g., "create_access_key")
            resource_from: How to extract resource identifier:
                - str: Attribute name from return value or first arg
                - Callable: Function to extract resource from (result, *args, **kwargs)
                - None: Use default resource identification
            log_success: Whether to log successful operations
            log_failure: Whether to log failed operations
            extract_details: Optional function to extract additional details
        """

        def decorator(func: F) -> F:
            # Common audit logging logic (DRY principle)
            def _audit_log(
                    self: Any,
                    result: Any,
                    args: tuple[Any, ...],
                    kwargs: dict[str, Any],
                    success: bool,
                    exception: Exception | None,
            ) -> None:
                """Shared audit logging logic for sync and async wrappers."""
                # Only log if we have an audit logger and conditions are met
                if not (
                        hasattr(self, "_audit_logger")
                        and ((success and log_success) or (not success and log_failure))
                ):
                    return

                resource = AuditDecorator._extract_resource(
                    resource_from, result, args, kwargs, success, exception
                )

                details = (
                        AuditDecorator._extract_details(
                            extract_details, result, args, kwargs, success, exception
                        )
                        or {}
                )

                # Add success status and error info
                details["success"] = success
                if exception:
                    details["error"] = str(exception)
                    details["error_type"] = type(exception).__name__

                # Get correlation_id if available
                correlation_id = getattr(self, "_correlation_id", None)

                self._audit_logger.log_action(
                    action=action,
                    resource=resource,
                    details=details,
                    correlation_id=correlation_id,
                )

            @wraps(func)
            async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                result, success, exception = None, False, None
                try:
                    result = await func(self, *args, **kwargs)
                    success = True
                    return result
                except Exception as e:
                    exception = e
                    success = False
                    raise
                finally:
                    _audit_log(self, result, args, kwargs, success, exception)

            @wraps(func)
            def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                result, success, exception = None, False, None
                try:
                    result = func(self, *args, **kwargs)
                    success = True
                    return result
                except Exception as e:
                    exception = e
                    success = False
                    raise
                finally:
                    _audit_log(self, result, args, kwargs, success, exception)

            # Return appropriate wrapper based on function type
            return cast(
                F, async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
            )

        return decorator

    @staticmethod
    def _extract_resource(
            resource_from: str | Callable | None,
            result: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
            success: bool,
            exception: Exception | None,
    ) -> str:
        """Extract resource identifier using specified strategy."""
        if resource_from is None:
            return "unknown"

        try:
            if isinstance(resource_from, str):
                # Try to get from result first
                if success and result is not None:
                    if hasattr(result, resource_from):
                        return str(getattr(result, resource_from))
                    if isinstance(result, dict) and resource_from in result:
                        return str(result[resource_from])

                # Try from first argument (usually the resource ID)
                if args and len(args) > 0:
                    return str(args[0])

                # Try from kwargs
                if resource_from in kwargs:
                    return str(kwargs[resource_from])

                return resource_from

            if callable(resource_from):
                return str(resource_from(result, *args, **kwargs))

        except Exception as e:
            logger.debug(f"Failed to extract resource: {e}", exc_info=True)

        return "unknown"

    @staticmethod
    def _extract_details(
            extract_details: Callable | None,
            result: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
            success: bool,
            exception: Exception | None,
    ) -> dict[str, Any] | None:
        """Extract additional details for audit log."""
        if extract_details is None:
            return None

        try:
            return extract_details(result, *args, **kwargs)
        except Exception as e:
            logger.debug(f"Failed to extract details: {e}", exc_info=True)
            return None

    @staticmethod
    def sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive data from audit logs.

        Uses lazy copying for performance - only creates new dict if needed.
        """
        if not details:
            return details

        keys_lower = {k.lower() for k in DEFAULT_SENSITIVE_KEYS}

        sanitized = details
        needs_copy = False

        for key, value in details.items():
            # Check if key contains sensitive terms
            if any(sensitive in key.lower() for sensitive in keys_lower):
                if not needs_copy:
                    sanitized = details.copy()
                    needs_copy = True
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                nested = AuditDecorator.sanitize_details(value)
                if nested is not value:  # Changed
                    if not needs_copy:
                        sanitized = details.copy()
                        needs_copy = True
                    sanitized[key] = nested

        return sanitized


# ===== Singleton Manager =====


_default_audit_logger: AuditLogger | None = None


def get_default_audit_logger() -> AuditLogger:
    """Get or create singleton default audit logger.

    Thread-safe lazy initialization.
    """
    global _default_audit_logger
    if _default_audit_logger is None:
        _default_audit_logger = DefaultAuditLogger()
    return _default_audit_logger


def set_default_audit_logger(logger: AuditLogger) -> None:
    """Set custom default audit logger globally."""
    global _default_audit_logger
    _default_audit_logger = logger


__all__ = [
    "AuditDecorator",
    "AuditLogger",
    "DefaultAuditLogger",
    "NoOpAuditLogger",
    "get_default_audit_logger",
    "set_default_audit_logger",
]
