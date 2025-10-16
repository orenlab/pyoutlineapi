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
import time
import uuid
from asyncio import Semaphore
from contextvars import ContextVar
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    NoReturn,
    ParamSpec,
    Protocol,
    TypeVar,
)
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

P = ParamSpec("P")
T = TypeVar("T")

# Context variable for correlation ID
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


# ===== Metrics Collector Protocol =====


class MetricsCollector(Protocol):
    """Protocol for metrics collection."""

    def increment(self, metric: str, *, tags: MetricsTags | None = None) -> None:
        """Increment counter metric."""
        ...

    def timing(
        self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """Record timing metric."""
        ...

    def gauge(
        self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """Set gauge metric."""
        ...


class NoOpMetrics:
    """No-op metrics collector (default)."""

    def increment(self, metric: str, *, tags: MetricsTags | None = None) -> None:
        pass

    def timing(
        self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        pass

    def gauge(
        self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        pass


# ===== Rate Limiter =====


class RateLimiter:
    """Rate limiter with dynamic limit adjustment."""

    __slots__ = ("_limit", "_lock", "_semaphore")

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._semaphore = Semaphore(limit)
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> RateLimiter:
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._semaphore.release()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def available(self) -> int:
        """Get available slots (safe access to internal state)."""
        try:
            return getattr(self._semaphore, "_value", 0)
        except AttributeError:
            logger.warning("Cannot access semaphore value")
            return 0

    @property
    def active(self) -> int:
        return self._limit - self.available

    async def set_limit(self, new_limit: int) -> None:
        if new_limit < 1:
            raise ValueError("Rate limit must be at least 1")

        async with self._lock:
            self._limit = new_limit
            self._semaphore = Semaphore(new_limit)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Rate limit changed to {new_limit}")


def _ensure_session(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Ensure session is initialized before operation."""

    @wraps(func)
    async def wrapper(self: BaseHTTPClient, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._session or self._session.closed:
            raise RuntimeError("Client session not initialized")
        if self._shutdown_event.is_set():
            raise RuntimeError("Client is shutting down")
        return await func(self, *args, **kwargs)

    return wrapper


# ===== Base HTTP Client =====


class BaseHTTPClient:
    """Enhanced base HTTP client with enterprise features.

    FEATURES:
    - Unified audit logging (via audit module)
    - Correlation ID tracking
    - Metrics collection
    - Graceful shutdown
    - Circuit breaker (optional)
    - Rate limiting
    """

    __slots__ = (
        "_active_requests",
        "_api_url",
        "_audit_logger",
        "_cert_sha256",
        "_circuit_breaker",
        "_enable_logging",
        "_max_connections",
        "_metrics",
        "_rate_limiter",
        "_retry_attempts",
        "_session",
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
        """Initialize base HTTP client with enterprise features."""
        self._api_url = Validators.validate_url(api_url).rstrip("/")
        self._cert_sha256 = Validators.validate_cert_fingerprint(cert_sha256)

        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._retry_attempts = retry_attempts
        self._max_connections = max_connections
        self._user_agent = user_agent or Constants.DEFAULT_USER_AGENT
        self._enable_logging = enable_logging

        self._session: aiohttp.ClientSession | None = None
        self._circuit_breaker: CircuitBreaker | None = None

        if circuit_config is not None:
            self._init_circuit_breaker(circuit_config)

        self._rate_limiter = RateLimiter(rate_limit)
        self._audit_logger = audit_logger or NoOpAuditLogger()
        self._metrics = metrics or NoOpMetrics()

        # Graceful shutdown support
        self._active_requests: set[asyncio.Task[Any]] = set()
        self._shutdown_event = asyncio.Event()

    def _init_circuit_breaker(self, config: CircuitConfig) -> None:
        """Initialize circuit breaker with adjusted timeout."""
        from .circuit_breaker import CircuitBreaker, CircuitConfig

        max_retry_time = self._timeout.total * (self._retry_attempts + 1)
        max_delays = sum(
            Constants.DEFAULT_RETRY_DELAY * i
            for i in range(1, self._retry_attempts + 1)
        )
        cb_timeout = max_retry_time + max_delays + 5.0

        if config.call_timeout < cb_timeout:
            if self._enable_logging:
                logger.info(f"Adjusting circuit timeout to {cb_timeout}s")
            config = CircuitConfig(
                failure_threshold=config.failure_threshold,
                recovery_timeout=config.recovery_timeout,
                success_threshold=config.success_threshold,
                call_timeout=cb_timeout,
            )

        self._circuit_breaker = CircuitBreaker(
            name=f"outline-{urlparse(self._api_url).netloc}",
            config=config,
        )

    async def __aenter__(self) -> BaseHTTPClient:
        await self._init_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.shutdown()

    async def _init_session(self) -> None:
        """Initialize HTTP session."""
        connector = aiohttp.TCPConnector(
            ssl=self._create_ssl_context(),
            limit=self._max_connections,
            enable_cleanup_closed=True,
        )

        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            connector=connector,
            headers={"User-Agent": self._user_agent},
            raise_for_status=False,
        )

        if self._enable_logging:
            safe_url = Validators.sanitize_url_for_logging(self.api_url)
            logger.info(f"Session initialized for {safe_url}")

    def _create_ssl_context(self) -> Fingerprint:
        """Create SSL fingerprint for certificate validation."""
        try:
            return Fingerprint(binascii.unhexlify(self._cert_sha256.get_secret_value()))
        except binascii.Error as e:
            raise ValueError("Invalid certificate fingerprint format") from e

    @_ensure_session
    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: JsonPayload = None,
        params: QueryParams | None = None,
    ) -> ResponseData:
        """Make HTTP request with enterprise features.

        Features:
        - Correlation ID tracking
        - Metrics collection
        - Rate limiting
        - Circuit breaker
        - Audit logging (if needed at HTTP level)
        """
        # Generate/get correlation ID
        cid = correlation_id.get() or str(uuid.uuid4())
        correlation_id.set(cid)

        # Rate limiting
        async with self._rate_limiter:
            # Track active request
            task = asyncio.current_task()
            if task:
                self._active_requests.add(task)

            try:
                # Use circuit breaker if available
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

                # Direct call
                return await self._do_request(
                    method, endpoint, json=json, params=params, correlation_id=cid
                )

            finally:
                if task:
                    self._active_requests.discard(task)

    async def _do_request(
        self,
        method: str,
        endpoint: str,
        *,
        json: JsonPayload = None,
        params: QueryParams | None = None,
        correlation_id: str,
    ) -> ResponseData:
        """Execute HTTP request with metrics and tracing."""
        url = self._build_url(endpoint)
        start_time = time.time()

        async def _make_request() -> ResponseData:
            try:
                # Add correlation ID to headers
                headers = {
                    "X-Correlation-ID": correlation_id,
                    "X-Request-ID": str(uuid.uuid4()),
                }

                async with self._session.request(  # type: ignore[union-attr]
                    method, url, json=json, params=params, headers=headers
                ) as response:
                    duration = time.time() - start_time

                    if self._enable_logging:
                        safe_endpoint = Validators.sanitize_endpoint_for_logging(
                            endpoint
                        )
                        logger.debug(
                            f"[{correlation_id}] {method} {safe_endpoint} -> {response.status}",
                            extra={"correlation_id": correlation_id},
                        )

                    # Metrics
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
                    except aiohttp.ContentTypeError:
                        return {"success": True}

            except asyncio.TimeoutError as e:
                duration = time.time() - start_time
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
                raise OutlineConnectionError(
                    f"Failed to connect: {e}",
                    host=urlparse(url).netloc,
                ) from e

            except aiohttp.ClientError as e:
                self._metrics.increment(
                    "outline.request.client_error",
                    tags={"endpoint": endpoint, "error": type(e).__name__},
                )
                raise APIError(f"Request failed: {e}", endpoint=endpoint) from e

        return await self._retry_request(_make_request, endpoint)

    async def _retry_request(
        self,
        request_func: Callable[[], Awaitable[ResponseData]],
        endpoint: str,
    ) -> ResponseData:
        """Execute request with retry logic and metrics."""
        last_error: Exception | None = None

        for attempt in range(self._retry_attempts + 1):
            try:
                return await request_func()

            except (OutlineTimeoutError, OutlineConnectionError, APIError) as error:
                last_error = error

                if self._enable_logging:
                    logger.warning(
                        f"Request to {endpoint} failed "
                        f"(attempt {attempt + 1}/{self._retry_attempts + 1}): {error}"
                    )

                if (
                    isinstance(error, APIError)
                    and error.status_code not in Constants.RETRY_STATUS_CODES
                ):
                    raise

                if attempt < self._retry_attempts:
                    delay = Constants.DEFAULT_RETRY_DELAY * (attempt + 1)
                    self._metrics.increment(
                        "outline.request.retry",
                        tags={"endpoint": endpoint, "attempt": str(attempt + 1)},
                    )
                    await asyncio.sleep(delay)

        self._metrics.increment(
            "outline.request.exhausted", tags={"endpoint": endpoint}
        )

        raise APIError(
            f"Request failed after {self._retry_attempts + 1} attempts",
            endpoint=endpoint,
        ) from last_error

    def _build_url(self, endpoint: str) -> str:
        return f"{self._api_url}/{endpoint.lstrip('/')}"

    @staticmethod
    async def _handle_error(response: ClientResponse, endpoint: str) -> NoReturn:
        """Handle error response and raise appropriate exception."""
        try:
            error_data = await response.json()
            message = error_data.get("message", response.reason)
        except (ValueError, aiohttp.ContentTypeError):
            message = response.reason or "Unknown error"

        raise APIError(message, status_code=response.status, endpoint=endpoint)

    # ===== Graceful Shutdown =====

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Graceful shutdown with timeout.

        Waits for active requests to complete before closing.
        """
        self._shutdown_event.set()

        if self._active_requests:
            logger.info(f"Waiting for {len(self._active_requests)} active requests...")

            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_requests, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Shutdown timeout, cancelling {len(self._active_requests)} requests"
                )
                for task in self._active_requests:
                    task.cancel()

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ===== Properties =====

    @property
    def api_url(self) -> str:
        parsed = urlparse(self._api_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def is_connected(self) -> bool:
        return self._session is not None and not self._session.closed

    @property
    def circuit_state(self) -> str | None:
        if self._circuit_breaker:
            return self._circuit_breaker.state.name
        return None

    @property
    def rate_limit(self) -> int:
        return self._rate_limiter.limit

    @property
    def active_requests(self) -> int:
        return len(self._active_requests)

    @property
    def available_slots(self) -> int:
        return self._rate_limiter.available

    # ===== Management Methods =====

    async def set_rate_limit(self, new_limit: int) -> None:
        await self._rate_limiter.set_limit(new_limit)

    def get_rate_limiter_stats(self) -> dict[str, int]:
        return {
            "limit": self._rate_limiter.limit,
            "active": len(self._active_requests),
            "available": self._rate_limiter.available,
        }

    async def reset_circuit_breaker(self) -> bool:
        if self._circuit_breaker:
            await self._circuit_breaker.reset()
            return True
        return False

    def get_circuit_metrics(self) -> dict[str, Any] | None:
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


__all__ = ["BaseHTTPClient", "MetricsCollector", "correlation_id"]
