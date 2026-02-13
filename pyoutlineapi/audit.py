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
import contextvars
import inspect
import logging
import time
from contextlib import suppress
from dataclasses import dataclass, field
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
from weakref import WeakValueDictionary

from .common_types import DEFAULT_SENSITIVE_KEYS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Type variables
P = ParamSpec("P")
R = TypeVar("R")

_audit_logger_context: contextvars.ContextVar[AuditLogger | None] = (
    contextvars.ContextVar("audit_logger", default=None)
)

_logger_cache: WeakValueDictionary[int, AuditLogger] = WeakValueDictionary()


# ===== Audit Context =====


@dataclass(slots=True, frozen=True)
class AuditContext:
    """Immutable audit context extracted from function call.

    Uses structural pattern matching and signature inspection for smart extraction.
    """

    action: str
    resource: str
    success: bool
    details: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None

    @classmethod
    def from_call(
        cls,
        func: Callable[..., Any],
        instance: object,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: object = None,
        exception: Exception | None = None,
    ) -> AuditContext:
        """Build audit context from function call with intelligent extraction.

        :param func: Function being audited
        :param instance: Instance (self) for methods
        :param args: Positional arguments
        :param kwargs: Keyword arguments
        :param result: Function result (if successful)
        :param exception: Exception (if failed)
        :return: Complete audit context
        """
        success = exception is None

        # Extract action from function name (snake_case -> action)
        action = func.__name__

        # Smart resource extraction
        resource = cls._extract_resource(func, args, kwargs, result, success)

        # Smart details extraction with automatic sanitization
        details = cls._extract_details(func, args, kwargs, result, exception, success)

        # Correlation ID from instance if available
        correlation_id = getattr(instance, "_correlation_id", None)

        return cls(
            action=action,
            resource=resource,
            success=success,
            details=details,
            correlation_id=correlation_id,
        )

    @staticmethod
    def _extract_resource(
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: object,
        success: bool,
    ) -> str:
        """Smart resource extraction using structural pattern matching.

        Priority:
        1. result.id (for create operations)
        2. Known resource parameter names (key_id, id, resource_id)
        3. First meaningful argument
        4. Function name analysis
        5. 'unknown' fallback

        :param func: Function being audited
        :param args: Positional arguments
        :param kwargs: Keyword arguments
        :param result: Function result
        :param success: Whether operation succeeded
        :return: Resource identifier
        """
        # Pattern 1: Extract from successful result
        if success and result is not None:
            match result:
                case _ if hasattr(result, "id"):
                    return str(result.id)
                case dict() if "id" in result:
                    return str(result["id"])

        # Pattern 2: Extract from known parameter names
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())

        # Skip 'self' and 'cls'
        params = [p for p in params if p not in ("self", "cls")]

        # Try common resource identifiers in priority order
        for resource_param in ("key_id", "id", "resource_id", "user_id", "name"):
            if resource_param in kwargs:
                return str(kwargs[resource_param])

        # Pattern 3: First meaningful parameter
        if params and params[0] in kwargs:
            return str(kwargs[params[0]])

        # Pattern 4: First positional argument (after self)
        if args:
            return str(args[0])

        # Pattern 5: Analyze function name for hints
        func_name = func.__name__.lower()
        if any(keyword in func_name for keyword in ("server", "global", "system")):
            return "server"

        return "unknown"

    @staticmethod
    def _extract_details(
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: object,
        exception: Exception | None,
        success: bool,
    ) -> dict[str, Any]:
        """Smart details extraction using signature introspection.

        Only includes meaningful parameters (excludes technical ones and None values).
        Automatically sanitizes sensitive data.

        :param func: Function being audited
        :param args: Positional arguments
        :param kwargs: Keyword arguments
        :param result: Function result
        :param exception: Exception if failed
        :param success: Whether operation succeeded
        :return: Sanitized details dictionary
        """
        details: dict[str, Any] = {"success": success}

        # Signature-based extraction
        sig = inspect.signature(func)

        # Parameters to exclude from details
        excluded = {"self", "cls", "as_json", "return_raw"}

        for param_name, param in sig.parameters.items():
            if param_name in excluded:
                continue

            # Get actual value
            value = kwargs.get(param_name)

            # Only include meaningful values (not None, not default)
            if value is not None and value != param.default:
                # Convert complex objects to simple representations
                match value:
                    case _ if hasattr(value, "model_dump"):
                        # Pydantic models
                        details[param_name] = value.model_dump(exclude_none=True)
                    case dict():
                        details[param_name] = value
                    case list() | tuple():
                        details[param_name] = len(value)  # Count, not content
                    case _:
                        details[param_name] = value

        # Add error information if present
        if exception:
            details["error"] = str(exception)
            details["error_type"] = type(exception).__name__

        # Sanitize sensitive data
        return _sanitize_details(details)


# ===== Audit Logger Protocol =====


@runtime_checkable
class AuditLogger(Protocol):
    """Protocol for audit logging implementations.

    Designed for async-first applications with sync fallback support.
    """

    async def alog_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Log auditable action asynchronously (primary method)."""
        ...  # pragma: no cover

    def log_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Log auditable action synchronously (fallback method)."""
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Gracefully shutdown logger."""
        ...  # pragma: no cover


# ===== Default Implementation =====


class DefaultAuditLogger:
    """Async audit logger with batching and backpressure handling."""

    __slots__ = (
        "_batch_size",
        "_batch_timeout",
        "_lock",
        "_queue",
        "_queue_size",
        "_shutdown_event",
        "_task",
    )

    def __init__(
        self,
        *,
        queue_size: int = 10000,
        batch_size: int = 100,
        batch_timeout: float = 1.0,
    ) -> None:
        """Initialize audit logger with batching support.

        :param queue_size: Maximum queue size (backpressure protection)
        :param batch_size: Maximum batch size for processing
        :param batch_timeout: Maximum time to wait for batch completion (seconds)
        """
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_size)
        self._queue_size = queue_size
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout
        self._task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()

    async def alog_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Log auditable action asynchronously with automatic batching.

        :param action: Action being performed
        :param resource: Resource identifier
        :param user: User performing the action (optional)
        :param details: Additional structured details (optional)
        :param correlation_id: Request correlation ID (optional)
        """
        if self._shutdown_event.is_set():
            # Fallback to sync logging during shutdown
            return self.log_action(
                action,
                resource,
                user=user,
                details=details,
                correlation_id=correlation_id,
            )

        # Ensure background task is running
        await self._ensure_task_running()

        # Build log entry
        entry = self._build_entry(action, resource, user, details, correlation_id)

        # Try to enqueue, handle backpressure
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            # Backpressure: log warning and use sync fallback
            if logger.isEnabledFor(logging.WARNING):
                logger.warning(
                    "[AUDIT] Queue full (%d items), using sync fallback",
                    self._queue_size,
                )
            self.log_action(
                action,
                resource,
                user=user,
                details=details,
                correlation_id=correlation_id,
            )

    def log_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Log auditable action synchronously (fallback method).

        :param action: Action being performed
        :param resource: Resource identifier
        :param user: User performing the action (optional)
        :param details: Additional structured details (optional)
        :param correlation_id: Request correlation ID (optional)
        """
        entry = self._build_entry(action, resource, user, details, correlation_id)
        self._write_log(entry)

    async def _ensure_task_running(self) -> None:
        """Ensure background processing task is running (lazy start with lock)."""
        if self._task is not None and not self._task.done():
            return

        async with self._lock:
            # Double-check after acquiring lock
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(
                    self._process_queue(), name="audit-logger"
                )

    async def _process_queue(self) -> None:
        """Background task for processing audit logs in batches.

        Uses batching for improved throughput and reduced I/O overhead.
        """
        batch: list[dict[str, Any]] = []

        try:
            while not self._shutdown_event.is_set():
                try:
                    # Wait for item with timeout for batch processing
                    entry = await asyncio.wait_for(
                        self._queue.get(), timeout=self._batch_timeout
                    )
                    batch.append(entry)

                    # Process batch when size reached or queue empty
                    if len(batch) >= self._batch_size or self._queue.empty():
                        self._write_batch(batch)
                        batch.clear()

                    self._queue.task_done()

                except asyncio.TimeoutError:
                    # Timeout: flush partial batch if any
                    if batch:
                        self._write_batch(batch)
                        batch.clear()

        except asyncio.CancelledError:
            # Flush remaining batch on cancellation
            if batch:
                self._write_batch(batch)
            raise
        finally:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("[AUDIT] Queue processor stopped")

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        """Write batch of log entries efficiently.

        :param batch: Batch of log entries to write
        """
        for entry in batch:
            self._write_log(entry)

    def _write_log(self, entry: dict[str, Any]) -> None:
        """Write single log entry to logger.

        :param entry: Log entry to write
        """
        message = self._format_message(entry)
        logger.info(message, extra=entry)

    @staticmethod
    def _build_entry(
        action: str,
        resource: str,
        user: str | None,
        details: dict[str, Any] | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        """Build structured log entry with sanitization.

        :param action: Action being performed
        :param resource: Resource identifier
        :param user: User performing action
        :param details: Additional details
        :param correlation_id: Correlation ID
        :return: Structured log entry
        """
        entry: dict[str, Any] = {
            "action": action,
            "resource": resource,
            "timestamp": time.time(),
            "is_audit": True,
        }

        if user is not None:
            entry["user"] = user
        if correlation_id is not None:
            entry["correlation_id"] = correlation_id
        if details is not None:
            entry["details"] = _sanitize_details(details)

        return entry

    @staticmethod
    def _format_message(entry: dict[str, Any]) -> str:
        """Format audit log message for human readability.

        :param entry: Log entry
        :return: Formatted message
        """
        action = entry["action"]
        resource = entry["resource"]
        user = entry.get("user")
        correlation_id = entry.get("correlation_id")

        parts = ["[AUDIT]", action, "on", resource]

        if user:
            parts.extend(["by", user])
        if correlation_id:
            parts.append(f"[{correlation_id}]")

        return " ".join(parts)

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        """Gracefully shutdown audit logger with queue draining.

        :param timeout: Maximum time to wait for queue to drain (seconds)
        """
        async with self._lock:
            if self._shutdown_event.is_set():
                return

            self._shutdown_event.set()

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("[AUDIT] Shutting down, draining queue")

            # Wait for queue to drain
            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout)
            except asyncio.TimeoutError:
                remaining = self._queue.qsize()
                if logger.isEnabledFor(logging.WARNING):
                    logger.warning(
                        "[AUDIT] Queue did not drain within %ss, %d items remaining",
                        timeout,
                        remaining,
                    )

            # Cancel processing task
            if self._task and not self._task.done():
                self._task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._task

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("[AUDIT] Shutdown complete")


# ===== No-Op Implementation =====


class NoOpAuditLogger:
    """Zero-overhead no-op audit logger.

    Implements AuditLogger protocol but performs no operations.
    Useful for disabling audit without code changes or performance impact.
    """

    __slots__ = ()

    async def alog_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """No-op async log."""

    def log_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """No-op sync log."""

    async def shutdown(self) -> None:
        """No-op shutdown."""


# ===== Professional Audit Decorator =====


def audited(
    *,
    log_success: bool = True,
    log_failure: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Audit logging decorator with zero-config smart extraction.

    Automatically extracts ALL information from function signature and execution:
    - Action name: from function name
    - Resource: from result.id, first parameter, or function analysis
    - Details: from function signature (excluding None and defaults)
    - Correlation ID: from instance._correlation_id if available
    - Success/failure: from exception handling

    Usage:
        @audited()
        async def create_access_key(self, name: str, port: int = 8080) -> AccessKey:
            # action: "create_access_key"
            # resource: result.id
            # details: {"name": "...", "port": 8080} (if not default)
            ...

        @audited(log_success=False)
        async def critical_operation(self, resource_id: str) -> bool:
            # Only logs failures for alerting
            ...

    :param log_success: Log successful operations (default: True)
    :param log_failure: Log failed operations (default: True)
    :return: Decorated function with automatic audit logging
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        # Determine if function is async at decoration time
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            async_func = cast("Callable[P, Awaitable[object]]", func)

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                # Check for audit logger on instance
                instance = args[0] if args else None
                audit_logger = getattr(instance, "_audit_logger", None)

                # No logger? Execute without audit
                if audit_logger is None:
                    return await async_func(*args, **kwargs)

                result: object | None = None

                try:
                    result = await async_func(*args, **kwargs)
                except Exception as e:
                    if log_failure:
                        ctx = AuditContext.from_call(
                            func=func,
                            instance=instance,
                            args=args,
                            kwargs=kwargs,
                            result=result,
                            exception=e,
                        )
                        task = asyncio.create_task(
                            audit_logger.alog_action(
                                action=ctx.action,
                                resource=ctx.resource,
                                details=ctx.details,
                                correlation_id=ctx.correlation_id,
                            )
                        )
                        task.add_done_callback(lambda t: t.exception())
                    raise
                else:
                    if log_success:
                        ctx = AuditContext.from_call(
                            func=func,
                            instance=instance,
                            args=args,
                            kwargs=kwargs,
                            result=result,
                            exception=None,
                        )
                        task = asyncio.create_task(
                            audit_logger.alog_action(
                                action=ctx.action,
                                resource=ctx.resource,
                                details=ctx.details,
                                correlation_id=ctx.correlation_id,
                            )
                        )
                        task.add_done_callback(lambda t: t.exception())
                    return result

            return cast("Callable[P, R]", async_wrapper)

        else:
            sync_func = cast("Callable[P, object]", func)

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                # Check for audit logger on instance
                instance = args[0] if args else None
                audit_logger = getattr(instance, "_audit_logger", None)

                # No logger? Execute without audit
                if audit_logger is None:
                    return sync_func(*args, **kwargs)

                result: object | None = None

                try:
                    result = sync_func(*args, **kwargs)
                except Exception as e:
                    if log_failure:
                        ctx = AuditContext.from_call(
                            func=func,
                            instance=instance,
                            args=args,
                            kwargs=kwargs,
                            result=result,
                            exception=e,
                        )
                        audit_logger.log_action(
                            action=ctx.action,
                            resource=ctx.resource,
                            details=ctx.details,
                            correlation_id=ctx.correlation_id,
                        )
                    raise
                else:
                    if log_success:
                        ctx = AuditContext.from_call(
                            func=func,
                            instance=instance,
                            args=args,
                            kwargs=kwargs,
                            result=result,
                            exception=None,
                        )
                        audit_logger.log_action(
                            action=ctx.action,
                            resource=ctx.resource,
                            details=ctx.details,
                            correlation_id=ctx.correlation_id,
                        )
                    return result

            return cast("Callable[P, R]", sync_wrapper)

    return decorator


# ===== Sanitization =====


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitize sensitive data using lazy copy-on-write.

    :param details: Dictionary to sanitize
    :return: Sanitized dictionary (maybe same instance if no changes)
    """
    if not details:
        return details

    # Pre-compute lowercase sensitive keys for performance
    sensitive_keys = {k.lower() for k in DEFAULT_SENSITIVE_KEYS}
    sanitized: dict[str, Any] | None = None

    for key, value in details.items():
        # Check if key contains sensitive pattern
        if any(pattern in key.lower() for pattern in sensitive_keys):
            # Lazy copy on first modification
            if sanitized is None:
                sanitized = dict(details)
            sanitized[key] = "***REDACTED***"
            continue

        # Recursively sanitize nested dicts
        if isinstance(value, dict):
            nested = _sanitize_details(value)
            if nested is not value:  # Only copy if changed
                if sanitized is None:
                    sanitized = dict(details)
                sanitized[key] = nested

    return sanitized or details


# ===== Context-based Logger Management =====


def set_audit_logger(logger_instance: AuditLogger) -> None:
    """Set audit logger for current async context.

    Thread-safe and async-safe using contextvars.
    Preferred over global state for high-load applications.

    :param logger_instance: Audit logger instance
    """
    _audit_logger_context.set(logger_instance)


def get_audit_logger() -> AuditLogger | None:
    """Get audit logger from current context.

    :return: Audit logger instance or None
    """
    return _audit_logger_context.get()


def get_or_create_audit_logger(instance_id: int | None = None) -> AuditLogger:
    """Get or create audit logger with weak reference caching.

    :param instance_id: Instance ID for caching (optional)
    :return: Audit logger instance
    """
    # Try context first
    ctx_logger = _audit_logger_context.get()
    if ctx_logger is not None:
        return ctx_logger

    # Try cache if instance_id provided
    if instance_id is not None:
        cached = _logger_cache.get(instance_id)
        if cached is not None:
            return cached

    # Create new logger
    logger_instance = DefaultAuditLogger()

    # Cache if instance_id provided
    if instance_id is not None:
        _logger_cache[instance_id] = cast(AuditLogger, logger_instance)

    return cast(AuditLogger, logger_instance)


__all__ = [
    "AuditContext",
    "AuditLogger",
    "DefaultAuditLogger",
    "NoOpAuditLogger",
    "audited",
    "get_audit_logger",
    "get_or_create_audit_logger",
    "set_audit_logger",
]
