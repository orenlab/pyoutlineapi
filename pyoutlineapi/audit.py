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
import contextlib
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
    runtime_checkable,
)

from .common_types import DEFAULT_SENSITIVE_KEYS

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Type variables
P = ParamSpec("P")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


# ===== Logging Utility =====


def _log_if_enabled(level: int, message: str, **kwargs: Any) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    :param kwargs: Additional logging kwargs
    """
    if logger.isEnabledFor(level):
        logger.log(level, message, **kwargs)


# ===== Audit Logger Protocol =====


@runtime_checkable
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
        """Log auditable action synchronously."""
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
        """Log auditable action asynchronously."""
        ...


# ===== Default Implementation =====


class DefaultAuditLogger:
    """Production-ready audit logger with async queue processing."""

    __slots__ = (
        "_enable_async",
        "_queue",
        "_queue_size",
        "_shutdown",
        "_shutdown_lock",
        "_task",
    )

    def __init__(self, *, enable_async: bool = True, queue_size: int = 1000) -> None:
        """Initialize audit logger.

        :param enable_async: Enable async logging queue for non-blocking operations
        :param queue_size: Maximum size of async logging queue (default: 1000)
        """
        self._enable_async = enable_async
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._task: asyncio.Task[None] | None = None
        self._queue_size = queue_size
        self._shutdown = False
        self._shutdown_lock = asyncio.Lock()

    def log_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Log auditable action synchronously.

        :param action: Action being performed (e.g., 'create_key', 'delete_key')
        :param resource: Resource identifier (e.g., key ID, server name)
        :param user: User performing the action (optional)
        :param details: Additional structured details about the action (optional)
        :param correlation_id: Request correlation ID for tracing (optional)
        """
        extra = self._prepare_extra(action, resource, user, details, correlation_id)
        message = self._build_message(action, resource, user, correlation_id, details)
        logger.info(message, extra=extra)

    async def alog_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Log auditable action asynchronously (non-blocking).

        Uses internal queue for high-performance async logging.
        Falls back to sync logging if queue is full or async is disabled.

        :param action: Action being performed (e.g., 'create_key', 'delete_key')
        :param resource: Resource identifier (e.g., key ID, server name)
        :param user: User performing the action (optional)
        :param details: Additional structured details about the action (optional)
        :param correlation_id: Request correlation ID for tracing (optional)
        """
        # Early return for disabled async or shutdown
        if not self._enable_async or self._shutdown:
            self.log_action(
                action,
                resource,
                user=user,
                details=details,
                correlation_id=correlation_id,
            )
            return

        # Lazy queue initialization
        await self._ensure_queue_initialized()

        extra = self._prepare_extra(action, resource, user, details, correlation_id)

        # Try non-blocking put, fallback to sync on full queue
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
            _log_if_enabled(
                logging.WARNING, "[AUDIT] Queue full, falling back to sync logging"
            )
            self.log_action(
                action,
                resource,
                user=user,
                details=details,
                correlation_id=correlation_id,
            )

    async def _ensure_queue_initialized(self) -> None:
        """Ensure queue is initialized (lazy initialization with lock)."""
        if self._queue is not None:
            return

        async with self._shutdown_lock:
            # Double-check after acquiring lock
            if self._queue is None and not self._shutdown:
                self._queue = asyncio.Queue(maxsize=self._queue_size)
                self._task = asyncio.create_task(self._process_queue())

    async def _process_queue(self) -> None:
        """Background task to process audit log queue."""
        try:
            while not self._shutdown:
                extra = await self._get_queue_item()

                if extra is None:
                    continue

                self._log_from_extra(extra)

                if self._queue:
                    self._queue.task_done()

        except asyncio.CancelledError:
            _log_if_enabled(logging.DEBUG, "[AUDIT] Queue processing cancelled")
            raise
        finally:
            _log_if_enabled(logging.DEBUG, "[AUDIT] Queue processing stopped")

    async def _get_queue_item(self) -> dict[str, Any] | None:
        """Get item from queue with timeout.

        :return: Queue item or None on timeout/error
        """
        try:
            item = await asyncio.wait_for(
                self._queue.get() if self._queue else asyncio.sleep(1),
                timeout=1.0,
            )
            return item if isinstance(item, dict) else None
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            _log_if_enabled(
                logging.ERROR,
                f"[AUDIT] Error getting queue item: {e}",
                exc_info=True,
            )
            return None

    def _log_from_extra(self, extra: dict[str, Any]) -> None:
        """Log audit message from extra dict.

        :param extra: Extra data with audit info
        """
        action = extra.get("action", "unknown")
        resource = extra.get("resource", "unknown")
        user = extra.get("user")
        correlation_id = extra.get("correlation_id")
        details = extra.get("details")

        message = self._build_message(action, resource, user, correlation_id, details)
        logger.info(message, extra=extra)

    @staticmethod
    def _build_message(
        action: str,
        resource: str,
        user: str | None,
        correlation_id: str | None,
        details: dict[str, Any] | None,
    ) -> str:
        """Build audit log message efficiently.

        :param action: Action being performed
        :param resource: Resource identifier
        :param user: User performing action (optional)
        :param correlation_id: Request correlation ID (optional)
        :param details: Additional details (optional)
        :return: Formatted message string
        """
        parts = ["[AUDIT]", action, "on", resource]

        if user:
            parts.extend(("by", user))
        if correlation_id:
            parts.append(f"[{correlation_id}]")
        if details:
            parts.append(f"| {details}")

        return " ".join(parts)

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        """Gracefully shutdown audit logger.

        Waits for queue to drain before shutting down the background task.

        :param timeout: Maximum time in seconds to wait for queue to drain
        """
        async with self._shutdown_lock:
            if self._shutdown:
                return

            self._shutdown = True
            _log_if_enabled(logging.DEBUG, "[AUDIT] Shutting down audit logger")

            await self._drain_queue(timeout)
            await self._cancel_task()

            _log_if_enabled(logging.DEBUG, "[AUDIT] Audit logger shutdown complete")

    async def _drain_queue(self, timeout: float) -> None:
        """Drain remaining queue items.

        :param timeout: Maximum time to wait
        """
        if not self._queue:
            return

        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            remaining = self._queue.qsize()
            _log_if_enabled(
                logging.WARNING,
                f"[AUDIT] Queue did not drain within {timeout}s, "
                f"{remaining} items remaining",
            )

    async def _cancel_task(self) -> None:
        """Cancel background processing task."""
        if not self._task or self._task.done():
            return

        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    @staticmethod
    def _prepare_extra(
        action: str,
        resource: str,
        user: str | None,
        details: dict[str, Any] | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        """Prepare structured logging context with sanitization.

        :param action: Action being performed
        :param resource: Resource identifier
        :param user: User performing action (optional)
        :param details: Additional details - will be sanitized (optional)
        :param correlation_id: Request correlation ID (optional)
        :return: Structured extra data for logger with is_audit flag
        """
        extra: dict[str, Any] = {
            "action": action,
            "resource": resource,
            "timestamp": time.time(),
            "is_audit": True,
        }

        if user is not None:
            extra["user"] = user
        if correlation_id is not None:
            extra["correlation_id"] = correlation_id
        if details is not None:
            extra["details"] = AuditDecorator.sanitize_details(details)

        return extra


# ===== No-Op Implementation =====


class NoOpAuditLogger:
    """No-op audit logger for when auditing is disabled.

    Implements AuditLogger protocol but performs no actual logging.
    Useful for disabling audit without code changes.
    """

    __slots__ = ()

    def log_action(self, action: str, resource: str, **_kwargs: Any) -> None:
        """Do nothing - audit logging disabled."""

    async def alog_action(self, action: str, resource: str, **_kwargs: Any) -> None:
        """Do nothing - audit logging disabled."""

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        """Do nothing - no cleanup needed."""


# ===== Audit Decorator =====


class AuditDecorator:
    """Universal audit logging decorator with modern Python patterns."""

    __slots__ = ()

    @staticmethod
    def audit_action(
        action: str,
        *,
        resource_from: str | Callable[..., str] | None = None,
        log_success: bool = True,
        log_failure: bool = True,
        extract_details: Callable[..., dict[str, Any] | None] | None = None,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]:
        """Decorator for automatic audit logging.

        Usage:
            @AuditDecorator.audit_action(
                "create_key",
                resource_from="id",
                extract_details=lambda result, *args, **kwargs: {"name": kwargs.get("name")}
            )
            async def create_access_key(self, name: str) -> AccessKey:
                ...

        :param action: Action name to log (e.g., 'create_key', 'delete_key')
        :param resource_from: How to extract resource identifier:
            - str: attribute/dict key name or literal value
            - Callable: function that extracts resource from (result, *args, **kwargs)
            - None: defaults to 'unknown'
        :param log_success: Whether to log successful operations (default: True)
        :param log_failure: Whether to log failed operations (default: True)
        :param extract_details: Optional function to extract additional details
            from (result, *args, **kwargs) -> dict[str, Any] | None
        :return: Decorated function with automatic audit logging
        """

        def decorator(func: Callable[P, T]) -> Callable[P, T]:
            def _audit_log(
                self: object,
                result: object,
                args: tuple[object, ...],
                kwargs: dict[str, object],
                success: bool,
                exception: Exception | None,
            ) -> None:
                """Shared audit logging logic."""
                # Guard clauses for early exit
                if not hasattr(self, "_audit_logger"):
                    return

                if not ((success and log_success) or (not success and log_failure)):
                    return

                # Extract and log
                resource = AuditDecorator._extract_resource(
                    resource_from, result, args, kwargs, success, exception
                )

                details_dict = AuditDecorator._build_details(
                    extract_details, result, args, kwargs, success, exception
                )

                correlation_id = getattr(self, "_correlation_id", None)

                self._audit_logger.log_action(  # type: ignore[attr-defined]
                    action=action,
                    resource=resource,
                    details=details_dict,
                    correlation_id=correlation_id,
                )

            @wraps(func)
            async def async_wrapper(
                self: object, *args: P.args, **kwargs: P.kwargs
            ) -> T:
                result: T | None = None
                success = False
                exception: Exception | None = None

                try:
                    result = await func(self, *args, **kwargs)  # type: ignore[misc]
                    success = True
                    return result
                except Exception as e:
                    exception = e
                    raise
                finally:
                    _audit_log(self, result, args, kwargs, success, exception)

            @wraps(func)
            def sync_wrapper(self: object, *args: P.args, **kwargs: P.kwargs) -> T:
                result: T | None = None
                success = False
                exception: Exception | None = None

                try:
                    result = func(self, *args, **kwargs)  # type: ignore[misc]
                    success = True
                    return result
                except Exception as e:
                    exception = e
                    raise
                finally:
                    _audit_log(self, result, args, kwargs, success, exception)

            return cast(
                Callable[P, T],
                async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper,
            )

        return decorator

    @staticmethod
    def _build_details(
        extract_details: Callable[..., dict[str, Any] | None] | None,
        result: object,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        success: bool,
        exception: Exception | None,
    ) -> dict[str, Any]:
        """Build details dict with success/failure info.

        :param extract_details: Optional function to extract custom details
        :param result: Function result (may be None if failed)
        :param args: Function positional arguments
        :param kwargs: Function keyword arguments
        :param success: Whether operation succeeded
        :param exception: Exception if operation failed (None if success)
        :return: Details dictionary with at least 'success' key
        """
        details: dict[str, Any] = {"success": success}

        # Add extracted details if available
        if extract_details:
            extracted = AuditDecorator._extract_details(
                extract_details, result, args, kwargs, success, exception
            )
            if extracted:
                details.update(extracted)

        # Add error info if present
        if exception:
            details["error"] = str(exception)
            details["error_type"] = type(exception).__name__

        return details

    @staticmethod
    def _extract_resource(
        resource_from: str | Callable[..., str] | None,
        result: object,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        success: bool,
        exception: Exception | None,
    ) -> str:
        """Extract resource identifier using pattern matching.

        :param resource_from: Extraction strategy (str attribute name, callable, or None)
        :param result: Function result (may be None if failed)
        :param args: Function positional arguments
        :param kwargs: Function keyword arguments
        :param success: Whether operation succeeded
        :param exception: Exception if operation failed
        :return: Resource identifier string or 'unknown' if extraction fails
        """
        if resource_from is None:
            return "unknown"

        try:
            # Pattern matching for extraction strategy
            match resource_from:
                case _ if callable(resource_from):
                    return str(resource_from(result, *args, **kwargs))
                case str(attr_name):
                    return (
                        AuditDecorator._extract_from_result(result, attr_name, success)
                        or AuditDecorator._extract_from_args(args, kwargs, attr_name)
                        or attr_name  # Fallback: use as literal
                    )
                case _:
                    return "unknown"

        except Exception as e:
            _log_if_enabled(
                logging.DEBUG,
                f"Resource extraction failed: {e}",
                exc_info=True,
            )
            return "unknown"

    @staticmethod
    def _extract_from_result(
        result: object,
        attr_name: str,
        success: bool,
    ) -> str | None:
        """Extract resource from result object.

        Only attempts extraction if operation was successful.

        :param result: Function result object
        :param attr_name: Attribute or dict key name to extract
        :param success: Whether operation succeeded
        :return: Extracted value as string, or None if extraction not possible
        """
        if not (success and result is not None):
            return None

        # Try attribute access
        if hasattr(result, attr_name):
            return str(getattr(result, attr_name))

        # Try dict access
        if isinstance(result, dict) and attr_name in result:
            return str(result[attr_name])

        return None

    @staticmethod
    def _extract_from_args(
        args: tuple[object, ...],
        kwargs: dict[str, object],
        attr_name: str,
    ) -> str | None:
        """Extract resource from function arguments.

        Tries kwargs first (more explicit), then falls back to first positional arg.

        :param args: Function positional arguments
        :param kwargs: Function keyword arguments
        :param attr_name: Name to look up in kwargs
        :return: Extracted value as string, or None if not found
        """
        # Try kwargs first (more explicit)
        if attr_name in kwargs:
            return str(kwargs[attr_name])

        # Fallback to first positional arg
        if args:
            return str(args[0])

        return None

    @staticmethod
    def _extract_details(
        extract_details: Callable[..., dict[str, Any] | None],
        result: object,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        success: bool,
        exception: Exception | None,
    ) -> dict[str, Any] | None:
        """Extract additional details for audit log.

        :param extract_details: User-provided extraction function
        :param result: Function result
        :param args: Function positional arguments
        :param kwargs: Function keyword arguments
        :param success: Whether operation succeeded
        :param exception: Exception if failed
        :return: Extracted details dict or None if extraction fails
        """
        try:
            return extract_details(result, *args, **kwargs)
        except Exception as e:
            _log_if_enabled(
                logging.DEBUG,
                f"Details extraction failed: {e}",
                exc_info=True,
            )
            return None

    @staticmethod
    def sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive data from audit logs using lazy copying.

        Recursively sanitizes nested dictionaries. Uses lazy copying for
        performance - only creates new dict when modifications are needed.

        Sensitive keys are matched case-insensitively against DEFAULT_SENSITIVE_KEYS
        (e.g., 'password', 'token', 'secret', 'api_key', etc.)

        :param details: Details dictionary to sanitize
        :return: Sanitized dictionary (may be same object if no changes needed)
        """
        if not details:
            return details

        keys_lower = {k.lower() for k in DEFAULT_SENSITIVE_KEYS}
        sanitized: dict[str, Any] | None = None

        for key, value in details.items():
            # Check for sensitive key
            if any(sensitive in key.lower() for sensitive in keys_lower):
                sanitized = sanitized or dict(details)  # Lazy copy
                sanitized[key] = "***REDACTED***"
                continue

            # Recursively sanitize nested dicts
            if isinstance(value, dict):
                nested = AuditDecorator.sanitize_details(value)
                if nested is not value:  # Only copy if changed
                    sanitized = sanitized or dict(details)
                    sanitized[key] = nested

        return sanitized or details


# ===== Singleton Manager =====


_default_audit_logger: AuditLogger | None = None


def get_default_audit_logger() -> AuditLogger:
    """Get or create singleton default audit logger.

    Thread-safe lazy initialization. Creates DefaultAuditLogger on first call.

    :return: Default audit logger instance (singleton)
    """
    global _default_audit_logger

    if _default_audit_logger is None:
        _default_audit_logger = DefaultAuditLogger()

    return _default_audit_logger


def set_default_audit_logger(logger_instance: AuditLogger) -> None:
    """Set custom default audit logger globally.

    Use this to replace the default audit logger with a custom implementation
    for all clients that don't explicitly specify an audit logger.

    :param logger_instance: Custom audit logger instance
    """
    global _default_audit_logger
    _default_audit_logger = logger_instance


__all__ = [
    "AuditDecorator",
    "AuditLogger",
    "DefaultAuditLogger",
    "NoOpAuditLogger",
    "get_default_audit_logger",
    "set_default_audit_logger",
]
