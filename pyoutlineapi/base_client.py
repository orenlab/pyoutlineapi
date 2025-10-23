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
import json
import logging
import secrets
import ssl
import time
from asyncio import Semaphore
from contextvars import ContextVar
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

import aiohttp
from aiohttp import ClientResponse, TraceRequestStartParams

from .audit import AuditLogger, NoOpAuditLogger
from .common_types import (
    Constants,
    CredentialSanitizer,
    JsonPayload,
    MetricsTags,
    QueryParams,
    ResponseData,
    SecureIDGenerator,
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

    from aiohttp import ClientSession, TraceConfig
    from pydantic import SecretStr

    from .circuit_breaker import CircuitBreaker, CircuitConfig

logger = logging.getLogger(__name__)

# Context variable for correlation ID tracking
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


class TokenBucketRateLimiter:
    """Token bucket algorithm for requests-per-second rate limiting.

    Thread-safe and optimized for async environment using event loop time.
    """

    __slots__ = ("_capacity", "_last_update", "_lock", "_rate", "_tokens")

    def __init__(
        self,
        rate: float = Constants.DEFAULT_RATE_LIMIT_RPS,
        capacity: int = Constants.DEFAULT_RATE_LIMIT_BURST,
    ) -> None:
        """Initialize rate limiter.

        :param rate: Tokens per second (requests/second)
        :param capacity: Maximum burst capacity
        :raises ValueError: If parameters are invalid
        """
        if rate <= 0:
            raise ValueError("Rate must be positive")
        if capacity <= 0:
            raise ValueError("Capacity must be positive")

        self._rate: float = rate
        self._capacity: int = capacity
        self._tokens: float = float(capacity)
        self._last_update: float = asyncio.get_event_loop().time()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquire tokens, waiting if necessary.

        :param tokens: Number of tokens to acquire
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_update

            # Refill tokens based on elapsed time
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_update = now

            # Wait if not enough tokens
            if self._tokens < tokens:
                wait_time = (tokens - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
            else:
                self._tokens -= tokens

    @property
    def available_tokens(self) -> float:
        """Get currently available tokens (approximate).

        :return: Number of available tokens
        """
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_update
        return min(self._capacity, self._tokens + elapsed * self._rate)


class RateLimiter:
    """Concurrent request limiter with dynamic limit adjustment."""

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
        """Get current rate limit."""
        return self._limit

    @property
    def available(self) -> int:
        """Get available slots."""
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
        """Get active operations count."""
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
        """Execute request with retry logic and comprehensive error metrics.

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

                # Error metrics tracking
                metrics.increment(
                    "outline.request.error",
                    tags={
                        "endpoint": endpoint,
                        "error_type": type(error).__name__,
                        "attempt": str(attempt + 1),
                    },
                )

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
                    # Track non-retryable errors
                    metrics.increment(
                        "outline.request.non_retryable",
                        tags={"endpoint": endpoint, "status": str(error.status_code)},
                    )
                    raise

                if attempt < retry_attempts:
                    delay = RetryHelper._calculate_delay(attempt)
                    metrics.increment(
                        "outline.request.retry",
                        tags={"endpoint": endpoint, "attempt": str(attempt + 1)},
                    )
                    await asyncio.sleep(delay)

        # Track exhausted retries
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


class SSLFingerprintValidator:
    """Enhanced SSL validation with fingerprint pinning.

    Note: Outline VPN uses self-signed certificates, so we disable CA verification
    but enforce strict fingerprint pinning for security.

    SECURITY NOTE: Accepts SecretStr to maintain secret in memory protection.
    Fingerprint is read only when needed and stored securely.
    """

    __slots__ = ("_expected_fingerprint_secret", "_ssl_context")

    def __init__(self, cert_sha256: SecretStr) -> None:
        """Initialize SSL validator with fingerprint pinning.

        :param cert_sha256: Pre-validated SHA-256 fingerprint as SecretStr

        Note: Fingerprint must be already validated by Validators.validate_cert_fingerprint().
              SecretStr is kept to maintain security - secret value is read only when needed.
        """
        self._expected_fingerprint_secret: SecretStr = cert_sha256

        # Create SSL context WITHOUT CA verification (self-signed certs)
        # Security is ensured by fingerprint pinning
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False  # We verify via fingerprint
        self._ssl_context.verify_mode = ssl.CERT_NONE  # Accept self-signed

        # Enforce minimum TLS 1.2
        self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Clean up sensitive data on exit."""
        # Clear sensitive data
        self._expected_fingerprint_secret, self._ssl_context = None, None

    @property
    @lru_cache(maxsize=128)
    def ssl_context(self) -> ssl.SSLContext:
        """Get SSL context for aiohttp."""
        return self._ssl_context

    @lru_cache(maxsize=512)
    def _verify_cert_fingerprint(self, cert_der: bytes) -> None:
        """Verify certificate fingerprint matches expected (DRY implementation).

        :param cert_der: Certificate in DER format
        :raises ValueError: If fingerprint doesn't match
        """
        import hashlib

        actual_fingerprint = hashlib.sha256(cert_der).hexdigest()

        expected_fingerprint = self._expected_fingerprint_secret.get_secret_value()

        if not secrets.compare_digest(actual_fingerprint, expected_fingerprint):
            raise ValueError(
                "Certificate fingerprint mismatch - possible MITM attack detected"
            )

    async def verify_connection(
        self,
        session: ClientSession,
        trace_config_ctx: TraceConfig,
        params: TraceRequestStartParams,
    ) -> None:
        """Verify certificate fingerprint during connection (MITM prevention).

        Called by aiohttp trace callback on request start.

        :param session: aiohttp session
        :param trace_config_ctx: Trace context
        :param params: Request parameters
        :raises ValueError: If fingerprint doesn't match
        """
        # Get peer certificate from connection
        connection = getattr(params, "connection", None)
        if connection is None:
            return

        transport = getattr(connection, "transport", None)
        if transport is None:
            return

        ssl_object = transport.get_extra_info("ssl_object")
        if ssl_object is None:
            return

        # Get certificate in DER format
        cert_der = ssl_object.getpeercert(binary_form=True)
        if cert_der:
            self._verify_cert_fingerprint(cert_der)


class BaseHTTPClient:
    """Enhanced base HTTP client with comprehensive security features."""

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
        "_rate_limiter_tps",
        "_retry_attempts",
        "_retry_helper",
        "_session",
        "_session_lock",
        "_shutdown_event",
        "_ssl_validator",
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
        """Initialize base HTTP client with enhanced security.

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
        # Use Validators from common_types (DRY!)
        self._api_url = Validators.validate_url(api_url).rstrip("/")

        # Validate fingerprint once
        # Keep as SecretStr for security - never expose as plain string
        self._cert_sha256 = Validators.validate_cert_fingerprint(cert_sha256)

        self._validate_numeric_params(timeout, retry_attempts, max_connections)

        self._timeout = aiohttp.ClientTimeout(total=float(timeout))
        self._retry_attempts = retry_attempts
        self._max_connections = max_connections
        self._user_agent = user_agent or Constants.DEFAULT_USER_AGENT
        self._enable_logging = enable_logging

        # Pass SecretStr directly - maintains security, no string exposure
        self._ssl_validator = SSLFingerprintValidator(self._cert_sha256)

        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self._circuit_breaker: CircuitBreaker | None = None

        if circuit_config is not None:
            self._init_circuit_breaker(circuit_config)

        self._rate_limiter = RateLimiter(rate_limit)

        self._rate_limiter_tps = TokenBucketRateLimiter()

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
            adjusted_config = CircuitConfig(
                failure_threshold=config.failure_threshold,
                recovery_timeout=config.recovery_timeout,
                success_threshold=config.success_threshold,
                call_timeout=cb_timeout,
            )
            self._circuit_breaker = CircuitBreaker("outline_api", adjusted_config)
        else:
            self._circuit_breaker = CircuitBreaker("outline_api", config)

    async def __aenter__(self) -> BaseHTTPClient:
        """Context manager entry - initialize session."""
        await self._ensure_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Context manager exit - cleanup session."""
        await self.shutdown()

    async def _ensure_session(self) -> None:
        """Ensure aiohttp session is initialized with enhanced security."""
        if self._session is not None and not self._session.closed:
            return

        async with self._session_lock:
            if self._session is not None and not self._session.closed:
                return

            connector = aiohttp.TCPConnector(
                ssl=self._ssl_validator.ssl_context,
                limit=self._max_connections,
                limit_per_host=max(1, self._max_connections // 2),
                ttl_dns_cache=Constants.DNS_CACHE_TTL,
                enable_cleanup_closed=True,
                force_close=False,  # Reuse connections for performance
            )

            # Setup trace config for fingerprint verification (MITM prevention)
            trace_config = aiohttp.TraceConfig()
            trace_config.on_request_start.append(self._ssl_validator.verify_connection)

            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
                raise_for_status=False,
                trace_configs=[trace_config],
            )

            _log_if_enabled(logging.DEBUG, "HTTP session initialized!")

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: JsonPayload = None,
        params: QueryParams | None = None,
    ) -> ResponseData:
        """Make HTTP request.

        :param method: HTTP method
        :param endpoint: API endpoint path
        :param json: JSON payload
        :param params: Query parameters
        :return: Response data
        :raises APIError: If request fails
        :raises CircuitOpenError: If circuit breaker is open
        :raises TimeoutError: If request times out
        :raises ConnectionError: If connection fails
        """
        await self._ensure_session()

        # Generate secure correlation ID
        request_id = SecureIDGenerator.generate_correlation_id()
        correlation_id.set(request_id)

        # Apply token bucket rate limiting
        await self._rate_limiter_tps.acquire()

        if self._circuit_breaker:
            try:
                return await self._circuit_breaker.call(
                    self._make_request_inner,
                    method,
                    endpoint,
                    json=json,
                    params=params,
                    correlation_id=request_id,
                )
            except CircuitOpenError:
                # Track circuit breaker open event with detailed metrics
                self._metrics.increment(
                    "outline.circuit.open",
                    tags={"endpoint": endpoint, "method": method},
                )
                _log_if_enabled(
                    logging.ERROR,
                    f"Circuit breaker OPEN for {endpoint} - rejecting request",
                )
                raise

        return await self._make_request_inner(
            method, endpoint, json=json, params=params, correlation_id=request_id
        )

    async def _make_request_inner(
        self,
        method: str,
        endpoint: str,
        *,
        json: JsonPayload = None,
        params: QueryParams | None = None,
        correlation_id: str,
    ) -> ResponseData:
        """Inner request method with size limits and validation.

        :param method: HTTP method
        :param endpoint: API endpoint
        :param json: JSON payload
        :param params: Query parameters
        :param correlation_id: Request correlation ID
        :return: Response data
        """

        async def _make_request() -> ResponseData:
            await self._ensure_session()

            url = self._build_url(endpoint)
            start_time = time.monotonic()

            # Track active request
            current_task = asyncio.current_task()
            if current_task:
                async with self._active_requests_lock:
                    self._active_requests.add(current_task)

            try:
                async with self._rate_limiter:
                    headers = {
                        "User-Agent": self._user_agent,
                        "X-Request-ID": correlation_id,
                        "X-Content-Type-Options": "nosniff",
                        "X-Frame-Options": "DENY",
                        "Accept": "application/json",
                    }

                    assert self._session is not None
                    async with self._session.request(
                        method, url, json=json, params=params, headers=headers
                    ) as response:
                        duration = time.monotonic() - start_time

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
                            # Track HTTP errors with detailed metrics
                            self._metrics.increment(
                                "outline.request.http_error",
                                tags={
                                    "method": method,
                                    "status": str(response.status),
                                    "endpoint": endpoint,
                                    "status_class": f"{response.status // 100}xx",
                                },
                            )
                            await self._handle_error(response, endpoint)

                        self._metrics.increment(
                            "outline.request.success",
                            tags={"method": method, "endpoint": endpoint},
                        )

                        if response.status == 204:
                            return {"success": True}

                        return await self._parse_response_safe(response, endpoint)

            except asyncio.TimeoutError as e:
                duration = time.monotonic() - start_time

                # Track timeout with metrics
                self._metrics.timing(
                    "outline.request.timeout",
                    duration,
                    tags={"method": method, "endpoint": endpoint},
                )
                self._metrics.increment(
                    "outline.request.timeout_error",
                    tags={
                        "endpoint": endpoint,
                        "method": method,
                        "timeout_value": str(self._timeout.total),
                    },
                )

                raise OutlineTimeoutError(
                    f"Request to {endpoint} timed out",
                    timeout=self._timeout.total,
                ) from e

            except aiohttp.ClientConnectionError as e:
                # Track connection errors with error type
                self._metrics.increment(
                    "outline.connection.error",
                    tags={
                        "endpoint": endpoint,
                        "error_type": type(e).__name__,
                        "method": method,
                    },
                )
                hostname = Validators.sanitize_url_for_logging(url)

                safe_message = CredentialSanitizer.sanitize(str(e))

                raise OutlineConnectionError(
                    f"Failed to connect: {safe_message}",
                    host=hostname,
                ) from e

            except aiohttp.ClientError as e:
                # Track client errors with detailed categorization
                self._metrics.increment(
                    "outline.request.client_error",
                    tags={
                        "endpoint": endpoint,
                        "error_type": type(e).__name__,
                        "method": method,
                    },
                )

                safe_message = CredentialSanitizer.sanitize(str(e))

                raise APIError(
                    f"Request failed: {safe_message}", endpoint=endpoint
                ) from e

            finally:
                # Remove from active requests
                if current_task:
                    async with self._active_requests_lock:
                        self._active_requests.discard(current_task)

        return await self._retry_helper.execute_with_retry(
            _make_request, endpoint, self._retry_attempts, self._metrics
        )

    @staticmethod
    async def _parse_response_safe(
        response: ClientResponse, endpoint: str
    ) -> ResponseData:
        """Parse response with size limits and validation.

        :param response: HTTP response
        :param endpoint: API endpoint
        :return: Parsed JSON data
        :raises APIError: If parsing fails or size exceeds limit
        """
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > Constants.MAX_RESPONSE_SIZE:
            raise APIError(
                f"Response too large: {content_length} bytes "
                f"(max {Constants.MAX_RESPONSE_SIZE})",
                status_code=response.status,
                endpoint=endpoint,
            )

        # Validate Content-Type
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and "application/json" not in content_type:
            _log_if_enabled(
                logging.WARNING,
                f"Unexpected Content-Type: {content_type}",
            )
        chunks = []
        total_size = 0

        async for chunk in response.content.iter_chunked(
            Constants.MAX_RESPONSE_CHUNK_SIZE
        ):
            total_size += len(chunk)
            if total_size > Constants.MAX_RESPONSE_SIZE:
                raise APIError(
                    f"Response exceeded size limit: {total_size} bytes",
                    status_code=response.status,
                    endpoint=endpoint,
                )
            chunks.append(chunk)

        data = b"".join(chunks)

        try:
            return json.loads(data)
        except (json.JSONDecodeError, ValueError) as e:
            if 200 <= response.status < 300:
                return {"success": True}
            raise APIError(
                f"Invalid JSON response from {endpoint}: {e}",
                status_code=response.status,
                endpoint=endpoint,
            ) from e

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

        safe_message = CredentialSanitizer.sanitize(message)

        raise APIError(safe_message, status_code=response.status, endpoint=endpoint)

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
        """Get sanitized API URL without secret path."""
        return Validators.sanitize_url_for_logging(self._api_url)

    @property
    def is_connected(self) -> bool:
        """Check if session is connected."""
        return self._session is not None and not self._session.closed

    @property
    def circuit_state(self) -> str | None:
        """Get circuit breaker state."""
        if self._circuit_breaker:
            return self._circuit_breaker.state.name
        return None

    @property
    def rate_limit(self) -> int:
        """Get current rate limit."""
        return self._rate_limiter.limit

    @property
    def active_requests(self) -> int:
        """Get number of active requests."""
        return len(self._active_requests)

    @property
    def available_slots(self) -> int:
        """Get number of available rate limit slots."""
        return self._rate_limiter.available

    async def set_rate_limit(self, new_limit: int) -> None:
        """Change rate limit dynamically."""
        await self._rate_limiter.set_limit(new_limit)

    def get_rate_limiter_stats(self) -> dict[str, int | float]:
        """Get comprehensive rate limiter statistics.

        NEW (2025): Includes token bucket metrics.
        """
        return {
            "limit": self._rate_limiter.limit,
            "active": len(self._active_requests),
            "available": self._rate_limiter.available,
            "tokens_available": self._rate_limiter_tps.available_tokens,
        }

    async def reset_circuit_breaker(self) -> bool:
        """Reset circuit breaker to closed state."""
        if self._circuit_breaker:
            await self._circuit_breaker.reset()
            return True
        return False

    def get_circuit_metrics(self) -> dict[str, int | float | str] | None:
        """Get circuit breaker metrics."""
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


__all__ = ["BaseHTTPClient", "MetricsCollector", "correlation_id", "NoOpMetrics"]
