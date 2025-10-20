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
import binascii
import logging
import secrets
import uuid
from asyncio import Semaphore
from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientResponse, Fingerprint

from .audit import AuditLogger, NoOpAuditLogger
from .common_types import (
    Constants,
    JsonPayload,
    MetricsTags,
    QueryParams,
    ResponseData,
    Validators,
)
from .exceptions import (
    APIError,
    CircuitOpenError,
    ConnectionError as OutlineConnectionError,
    TimeoutError as OutlineTimeoutError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic import SecretStr

    from .circuit_breaker import CircuitBreaker, CircuitConfig

logger = logging.getLogger(__name__)

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def _log_if_enabled(level: int, message: str, **kwargs: object) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    :param kwargs: Additional logging kwargs
    """
    if logger.isEnabledFor(level):
        logger.log(level, message, **kwargs)


class MetricsCollector(Protocol):
    """Protocol for metrics collection."""

    def increment(self, metric: str, *, tags: MetricsTags | None = None) -> None:
        """Increment counter metric.

        :param metric: Metric name
        :param tags: Optional metric tags
        """
        ...

    def timing(
            self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """Record timing metric.

        :param metric: Metric name
        :param value: Timing value in seconds
        :param tags: Optional metric tags
        """
        ...

    def gauge(
            self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """Set gauge metric.

        :param metric: Metric name
        :param value: Gauge value
        :param tags: Optional metric tags
        """
        ...


class NoOpMetrics:
    """No-op metrics collector (default)."""

    __slots__ = ()

    def increment(self, metric: str, *, tags: MetricsTags | None = None) -> None:
        """No-op increment."""

    def timing(
            self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """No-op timing."""

    def gauge(
            self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """No-op gauge."""


class RateLimiter:
    """Rate limiter with dynamic limit adjustment and thread-safety."""

    __slots__ = ("_limit", "_lock", "_semaphore")

    def __init__(self, limit: int) -> None:
        """Initialize rate limiter.

        :param limit: Maximum concurrent operations
        :raises ValueError: If limit is less than 1
        """
        if limit < 1:
            raise ValueError("Rate limit must be at least 1")

        self._limit = limit
        self._semaphore = Semaphore(limit)
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> RateLimiter:
        """Enter rate limiter context."""
        await self._semaphore.acquire()
        return self

    async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object | None,
    ) -> None:
        """Exit rate limiter context."""
        self._semaphore.release()

    @property
    def limit(self) -> int:
        """Get current rate limit.

        :return: Maximum concurrent operations
        """
        return self._limit

    @property
    def available(self) -> int:
        """Get available slots.

        :return: Number of available slots
        """
        try:
            value = getattr(self._semaphore, "_value", None)
            return value if isinstance(value, int) else 0
        except (AttributeError, TypeError):
            _log_if_enabled(
                logging.WARNING,
                "Cannot access semaphore value",
                exc_info=True,
            )
            return 0

    @property
    def active(self) -> int:
        """Get active operations count.

        :return: Number of active operations
        """
        return max(0, self._limit - self.available)

    async def set_limit(self, new_limit: int) -> None:
        """Change rate limit dynamically.

        :param new_limit: New rate limit value
        :raises ValueError: If new_limit is less than 1
        """
        if new_limit < 1:
            raise ValueError("Rate limit must be at least 1")

        async with self._lock:
            if new_limit == self._limit:
                return

            old_limit = self._limit
            self._limit = new_limit
            self._semaphore = Semaphore(new_limit)

            _log_if_enabled(
                logging.DEBUG,
                f"Rate limit changed from {old_limit} to {new_limit}",
            )


class RetryHelper:
    """Helper class for retry logic with exponential backoff (DRY)."""

    __slots__ = ()

    @staticmethod
    async def execute_with_retry(
            func: Callable[[], Awaitable[ResponseData]],
            endpoint: str,
            retry_attempts: int,
            metrics: MetricsCollector,
    ) -> ResponseData:
        """Execute request with retry logic.

        :param func: Request function to execute
        :param endpoint: API endpoint
        :param retry_attempts: Number of retry attempts
        :param metrics: Metrics collector
        :return: Response data
        :raises APIError: If all retry attempts fail
        """
        last_error: Exception | None = None

        for attempt in range(retry_attempts + 1):
            try:
                return await func()

            except (OutlineTimeoutError, OutlineConnectionError, APIError) as error:
                last_error = error

                _log_if_enabled(
                    logging.WARNING,
                    f"Request to {endpoint} failed "
                    f"(attempt {attempt + 1}/{retry_attempts + 1}): {error}",
                )

                if (
                        isinstance(error, APIError)
                        and error.status_code
                        and error.status_code not in Constants.RETRY_STATUS_CODES
                ):
                    raise

                if attempt < retry_attempts:
                    delay = RetryHelper._calculate_delay(attempt)
                    metrics.increment(
                        "outline.request.retry",
                        tags={"endpoint": endpoint, "attempt": str(attempt + 1)},
                    )
                    await asyncio.sleep(delay)

        metrics.increment("outline.request.exhausted", tags={"endpoint": endpoint})

        raise APIError(
            f"Request failed after {retry_attempts + 1} attempts",
            endpoint=endpoint,
        ) from last_error

    @staticmethod
    def _calculate_delay(attempt: int) -> float:
        """Calculate retry delay with exponential backoff and jitter.

        :param attempt: Current attempt number
        :return: Delay in seconds
        """
        base_delay = Constants.DEFAULT_RETRY_DELAY * (attempt + 1)
        jitter = base_delay * 0.2 * (secrets.randbelow(40) - 20) / 100
        return max(0.1, base_delay + jitter)


class BaseHTTPClient:
    """Enhanced base HTTP client with enterprise features.

    Provides unified audit logging, correlation ID tracking, metrics collection,
    graceful shutdown, circuit breaker support, and rate limiting.

    Security features:
    - Certificate pinning via SHA-256 fingerprint
    - Secure random correlation IDs
    - Request tracking and timeout enforcement
    - Graceful shutdown to prevent data loss
    """

    __slots__ = (
        "_active_requests",
        "_active_requests_lock",
        "_api_url",
        "_audit_logger",
        "_cert_sha256",
        "_circuit_breaker",
        "_enable_logging",
        "_max_connections",
        "_metrics",
        "_rate_limiter",
        "_retry_attempts",
        "_retry_helper",
        "_session",
        "_session_lock",
        "_shutdown_event",
        "_timeout",
        "_user_agent",
    )

    def __init__(
            self,
            api_url: str,
            cert_sha256: SecretStr,
            *,
            timeout: int = Constants.DEFAULT_TIMEOUT,
            retry_attempts: int = Constants.DEFAULT_RETRY_ATTEMPTS,
            max_connections: int = Constants.DEFAULT_MAX_CONNECTIONS,
            user_agent: str | None = None,
            enable_logging: bool = False,
            circuit_config: CircuitConfig | None = None,
            rate_limit: int = 100,
            audit_logger: AuditLogger | None = None,
            metrics: MetricsCollector | None = None,
    ) -> None:
        """Initialize base HTTP client.

        :param api_url: Outline server API URL
        :param cert_sha256: SHA-256 certificate fingerprint
        :param timeout: Request timeout in seconds
        :param retry_attempts: Number of retry attempts
        :param max_connections: Connection pool size
        :param user_agent: Custom user agent string
        :param enable_logging: Enable debug logging
        :param circuit_config: Circuit breaker configuration
        :param rate_limit: Maximum concurrent requests
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :raises ValueError: If parameters are invalid
        """
        self._api_url = Validators.validate_url(api_url).rstrip("/")
        self._cert_sha256 = Validators.validate_cert_fingerprint(cert_sha256)

        self._validate_numeric_params(timeout, retry_attempts, max_connections)

        self._timeout = aiohttp.ClientTimeout(total=float(timeout))
        self._retry_attempts = retry_attempts
        self._max_connections = max_connections
        self._user_agent = user_agent or Constants.DEFAULT_USER_AGENT
        self._enable_logging = enable_logging

        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self._circuit_breaker: CircuitBreaker | None = None

        if circuit_config is not None:
            self._init_circuit_breaker(circuit_config)

        self._rate_limiter = RateLimiter(rate_limit)
        self._audit_logger = audit_logger or NoOpAuditLogger()
        self._metrics = metrics or NoOpMetrics()
        self._retry_helper = RetryHelper()

        self._active_requests: set[asyncio.Task[ResponseData]] = set()
        self._active_requests_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    @staticmethod
    def _validate_numeric_params(
            timeout: int, retry_attempts: int, max_connections: int
    ) -> None:
        """Validate numeric parameters (DRY).

        :param timeout: Timeout value
        :param retry_attempts: Retry attempts value
        :param max_connections: Max connections value
        :raises ValueError: If any parameter is invalid
        """
        if timeout < 1:
            raise ValueError("Timeout must be at least 1 second")
        if retry_attempts < 0:
            raise ValueError("Retry attempts cannot be negative")
        if max_connections < 1:
            raise ValueError("Max connections must be at least 1")

    def _init_circuit_breaker(self, config: CircuitConfig) -> None:
        """Initialize circuit breaker with adjusted timeout.

        :param config: Circuit breaker configuration
        """
        from .circuit_breaker import CircuitBreaker, CircuitConfig

        max_retry_time = self._timeout.total * (self._retry_attempts + 1)
        max_delays = sum(
            Constants.DEFAULT_RETRY_DELAY * (i + 1) for i in range(self._retry_attempts)
        )
        cb_timeout = max_retry_time + max_delays + 5.0

        if config.call_timeout < cb_timeout:
            _log_if_enabled(
                logging.INFO,
                f"Adjusting circuit timeout from {config.call_timeout}s "
                f"to {cb_timeout}s for safety",
            )
            config = CircuitConfig(
                failure_threshold=config.failure_threshold,
                recovery_timeout=config.recovery_timeout,
                success_threshold=config.success_threshold,
                call_timeout=cb_timeout,
            )

        hostname = urlparse(self._api_url).netloc or "unknown"
        self._circuit_breaker = CircuitBreaker(
            name=f"outline-{hostname}",
            config=config,
        )

    async def __aenter__(self) -> BaseHTTPClient:
        """Enter async context manager.

        :return: Self
        """
        await self._init_session()
        return self

    async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object | None,
    ) -> None:
        """Exit async context manager."""
        await self.shutdown()

    async def _init_session(self) -> None:
        """Initialize HTTP session with SSL context and thread-safety."""
        async with self._session_lock:
            if self._session is not None:
                return

            connector = aiohttp.TCPConnector(
                ssl=self._create_ssl_context(),
                limit=self._max_connections,
                enable_cleanup_closed=True,
                force_close=False,
                ttl_dns_cache=300,
            )

            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
                headers={"User-Agent": self._user_agent},
                raise_for_status=False,
                trust_env=False,
            )

            if self._enable_logging:
                safe_url = Validators.sanitize_url_for_logging(self.api_url)
                _log_if_enabled(logging.INFO, f"Session initialized for {safe_url}")

    def _create_ssl_context(self) -> Fingerprint:
        """Create SSL fingerprint for certificate validation.

        :return: SSL fingerprint
        :raises ValueError: If certificate fingerprint is invalid
        """
        try:
            fingerprint_bytes = binascii.unhexlify(self._cert_sha256.get_secret_value())
            return Fingerprint(fingerprint_bytes)
        except (binascii.Error, TypeError, ValueError) as e:
            raise ValueError("Invalid certificate fingerprint format") from e

    async def _ensure_session(self) -> None:
        """Ensure session is initialized.

        :raises RuntimeError: If session not initialized or shutting down
        """
        if not self._session or self._session.closed:
            raise RuntimeError("Client session not initialized")
        if self._shutdown_event.is_set():
            raise RuntimeError("Client is shutting down")

    async def _request(
            self,
            method: str,
            endpoint: str,
            *,
            json: JsonPayload = None,
            params: QueryParams | None = None,
    ) -> ResponseData:
        """Make HTTP request with enterprise features.

        :param method: HTTP method
        :param endpoint: API endpoint
        :param json: Request JSON payload
        :param params: Query parameters
        :return: Response data
        """
        await self._ensure_session()

        cid = correlation_id.get() or self._generate_correlation_id()
        correlation_id.set(cid)

        async with self._rate_limiter:
            task = asyncio.current_task()
            if task:
                async with self._active_requests_lock:
                    self._active_requests.add(task)

            try:
                if self._circuit_breaker:
                    try:
                        return await self._circuit_breaker.call(
                            self._do_request,
                            method,
                            endpoint,
                            json=json,
                            params=params,
                            correlation_id=cid,
                        )
                    except CircuitOpenError:
                        self._metrics.increment(
                            "outline.circuit.open", tags={"endpoint": endpoint}
                        )
                        raise

                return await self._do_request(
                    method, endpoint, json=json, params=params, correlation_id=cid
                )

            finally:
                if task:
                    async with self._active_requests_lock:
                        self._active_requests.discard(task)

    @staticmethod
    def _generate_correlation_id() -> str:
        """Generate cryptographically secure correlation ID.

        :return: Secure random correlation ID
        """
        return secrets.token_bytes(8).hex()

    async def _do_request(
            self,
            method: str,
            endpoint: str,
            *,
            json: JsonPayload = None,
            params: QueryParams | None = None,
            correlation_id: str,
    ) -> ResponseData:
        """Execute HTTP request with metrics and tracing.

        :param method: HTTP method
        :param endpoint: API endpoint
        :param json: Request JSON payload
        :param params: Query parameters
        :param correlation_id: Request correlation ID
        :return: Response data
        """
        url = self._build_url(endpoint)
        start_time = asyncio.get_event_loop().time()

        async def _make_request() -> ResponseData:
            try:
                headers = {
                    "X-Correlation-ID": correlation_id,
                    "X-Request-ID": str(uuid.uuid4()),
                }

                assert self._session is not None
                async with self._session.request(
                        method, url, json=json, params=params, headers=headers
                ) as response:
                    duration = asyncio.get_event_loop().time() - start_time

                    if self._enable_logging:
                        safe_endpoint = Validators.sanitize_endpoint_for_logging(
                            endpoint
                        )
                        _log_if_enabled(
                            logging.DEBUG,
                            f"[{correlation_id}] {method} {safe_endpoint} -> {response.status}",
                            extra={"correlation_id": correlation_id},
                        )

                    self._metrics.timing(
                        "outline.request.duration",
                        duration,
                        tags={"method": method, "endpoint": endpoint},
                    )

                    if response.status >= 400:
                        self._metrics.increment(
                            "outline.request.errors",
                            tags={
                                "method": method,
                                "status": str(response.status),
                                "endpoint": endpoint,
                            },
                        )
                        await self._handle_error(response, endpoint)

                    self._metrics.increment(
                        "outline.request.success",
                        tags={"method": method, "endpoint": endpoint},
                    )

                    if response.status == 204:
                        return {"success": True}

                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, ValueError):
                        if 200 <= response.status < 300:
                            return {"success": True}
                        raise APIError(
                            f"Invalid JSON response from {endpoint}",
                            status_code=response.status,
                            endpoint=endpoint,
                        ) from None

            except asyncio.TimeoutError as e:
                duration = asyncio.get_event_loop().time() - start_time
                self._metrics.timing(
                    "outline.request.timeout",
                    duration,
                    tags={"method": method, "endpoint": endpoint},
                )
                raise OutlineTimeoutError(
                    f"Request to {endpoint} timed out",
                    timeout=self._timeout.total,
                ) from e

            except aiohttp.ClientConnectionError as e:
                self._metrics.increment(
                    "outline.connection.error", tags={"endpoint": endpoint}
                )
                hostname = urlparse(url).netloc or "unknown"
                raise OutlineConnectionError(
                    f"Failed to connect: {e}",
                    host=hostname,
                ) from e

            except aiohttp.ClientError as e:
                self._metrics.increment(
                    "outline.request.client_error",
                    tags={"endpoint": endpoint, "error": type(e).__name__},
                )
                raise APIError(f"Request failed: {e}", endpoint=endpoint) from e

        return await self._retry_helper.execute_with_retry(
            _make_request, endpoint, self._retry_attempts, self._metrics
        )

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint.

        :param endpoint: API endpoint
        :return: Full URL
        """
        clean_endpoint = endpoint.lstrip("/")
        return f"{self._api_url}/{clean_endpoint}"

    @staticmethod
    async def _handle_error(response: ClientResponse, endpoint: str) -> None:
        """Handle error response and raise appropriate exception.

        :param response: HTTP response
        :param endpoint: API endpoint
        :raises APIError: Always raises with error details
        """
        try:
            error_data = await response.json()
            message = error_data.get("message", response.reason or "Unknown error")
        except (ValueError, aiohttp.ContentTypeError, TypeError):
            message = response.reason or "Unknown error"

        raise APIError(message, status_code=response.status, endpoint=endpoint)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Graceful shutdown with timeout.

        Waits for active requests to complete before closing.

        :param timeout: Maximum time to wait for active requests (seconds)
        """
        if self._shutdown_event.is_set():
            return

        self._shutdown_event.set()

        async with self._active_requests_lock:
            active_requests = list(self._active_requests)

        if active_requests:
            _log_if_enabled(
                logging.INFO,
                f"Waiting for {len(active_requests)} active requests...",
            )

            try:
                await asyncio.wait_for(
                    asyncio.gather(*active_requests, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                _log_if_enabled(
                    logging.WARNING,
                    f"Shutdown timeout, cancelling {len(active_requests)} requests",
                )
                for task in active_requests:
                    if not task.done():
                        task.cancel()

        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

        _log_if_enabled(logging.DEBUG, "HTTP client shutdown complete")

    @property
    def api_url(self) -> str:
        """Get sanitized API URL without secret path.

        :return: Sanitized API URL
        """
        parsed = urlparse(self._api_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def is_connected(self) -> bool:
        """Check if session is connected.

        :return: True if connected
        """
        return self._session is not None and not self._session.closed

    @property
    def circuit_state(self) -> str | None:
        """Get circuit breaker state.

        :return: Circuit state name or None if not enabled
        """
        if self._circuit_breaker:
            return self._circuit_breaker.state.name
        return None

    @property
    def rate_limit(self) -> int:
        """Get current rate limit.

        :return: Maximum concurrent requests
        """
        return self._rate_limiter.limit

    @property
    def active_requests(self) -> int:
        """Get number of active requests.

        :return: Active request count
        """
        return len(self._active_requests)

    @property
    def available_slots(self) -> int:
        """Get number of available rate limit slots.

        :return: Available slots count
        """
        return self._rate_limiter.available

    async def set_rate_limit(self, new_limit: int) -> None:
        """Change rate limit dynamically.

        :param new_limit: New rate limit value
        :raises ValueError: If new_limit is invalid
        """
        await self._rate_limiter.set_limit(new_limit)

    def get_rate_limiter_stats(self) -> dict[str, int]:
        """Get rate limiter statistics.

        :return: Statistics dictionary
        """
        return {
            "limit": self._rate_limiter.limit,
            "active": len(self._active_requests),
            "available": self._rate_limiter.available,
        }

    async def reset_circuit_breaker(self) -> bool:
        """Reset circuit breaker to closed state.

        :return: True if reset successful, False if not enabled
        """
        if self._circuit_breaker:
            await self._circuit_breaker.reset()
            return True
        return False

    def get_circuit_metrics(self) -> dict[str, int | float | str] | None:
        """Get circuit breaker metrics.

        :return: Metrics dictionary or None if not enabled
        """
        if not self._circuit_breaker:
            return None

        metrics = self._circuit_breaker.metrics
        return {
            "state": self._circuit_breaker.state.name,
            "total_calls": metrics.total_calls,
            "successful_calls": metrics.successful_calls,
            "failed_calls": metrics.failed_calls,
            "success_rate": metrics.success_rate,
        }


__all__ = [
    "BaseHTTPClient",
    "MetricsCollector",
    "correlation_id",
]
