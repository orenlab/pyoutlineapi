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
from contextlib import suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientResponse

from .audit import AuditLogger, NoOpAuditLogger
from .common_types import (
    Constants,
    CredentialSanitizer,
    JsonPayload,
    MetricsTags,
    QueryParams,
    ResponseData,
    SecureIDGenerator,
    SSRFProtection,
    Validators,
)
from .exceptions import (
    APIError,
    CircuitOpenError,
    OutlineConnectionError,
    OutlineTimeoutError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import SimpleNamespace

    from aiohttp import (
        ClientSession,
        TraceConnectionCreateEndParams,
        TraceConnectionReuseconnParams,
    )
    from pydantic import SecretStr

    from .circuit_breaker import CircuitBreaker, CircuitConfig

logger = logging.getLogger(__name__)

# Context variable for correlation ID tracking (thread-safe)
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


class MetricsCollector(Protocol):
    """Protocol for metrics collection.

    Allows dependency injection of custom metrics backends.
    """

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
    """No-op metrics collector (zero-overhead default).

    Uses __slots__ to minimize memory footprint.
    """

    __slots__ = ()

    def increment(self, metric: str, *, tags: MetricsTags | None = None) -> None:
        """No-op increment (zero overhead)."""

    def timing(
        self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """No-op timing (zero overhead)."""

    def gauge(
        self, metric: str, value: float, *, tags: MetricsTags | None = None
    ) -> None:
        """No-op gauge (zero overhead)."""


class TokenBucketRateLimiter:
    """Token bucket algorithm for requests-per-second rate limiting."""

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
        self._last_update: float = time.monotonic()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquire tokens, waiting if necessary.

        Uses monotonic clock for accurate timing.

        :param tokens: Number of tokens to acquire
        """
        async with self._lock:
            # Cache loop reference (minor optimization)
            now = time.monotonic()
            elapsed = now - self._last_update

            # Refill tokens based on elapsed time (O(1) calculation)
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
        """Get currently available tokens (approximate, lock-free).

        Lock-free read for minimal overhead. May be slightly stale.

        :return: Number of available tokens
        """
        now = time.monotonic()
        elapsed = now - self._last_update
        return min(self._capacity, self._tokens + elapsed * self._rate)


class RateLimiter:
    """Concurrent request limiter with dynamic limit adjustment.

    Uses Semaphore for efficient concurrent limiting.
    """

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
        """Get available slots (lock-free read).

        Uses getattr for safety - may return 0 if unable to read.
        """
        try:
            value = getattr(self._semaphore, "_value", None)
            return value if isinstance(value, int) else 0
        except (AttributeError, TypeError):
            if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                logger.warning("Cannot access semaphore value", exc_info=True)
            return 0

    @property
    def active(self) -> int:
        """Get active operations count."""
        return max(0, self._limit - self.available)

    async def set_limit(self, new_limit: int) -> None:
        """Change rate limit dynamically.

        Creates new semaphore to avoid complex state management.

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

            if logger.isEnabledFor(Constants.LOG_LEVEL_DEBUG):
                logger.debug("Rate limit changed from %d to %d", old_limit, new_limit)


class RetryHelper:
    """Helper class for retry logic with exponential backoff."""

    __slots__ = ()

    @staticmethod
    async def execute_with_retry(
        func: Callable[[], Awaitable[ResponseData]],
        endpoint: str,
        retry_attempts: int,
        metrics: MetricsCollector,
    ) -> ResponseData:
        """Execute request with retry logic and comprehensive error metrics.

        Implements exponential backoff with jitter for distributed systems.

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

                # Track error metrics
                metrics.increment(
                    "outline.request.error",
                    tags={
                        "endpoint": endpoint,
                        "error_type": type(error).__name__,
                        "attempt": str(attempt + 1),
                    },
                )

                if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                    logger.warning(
                        "Request to %s failed (attempt %d/%d): %s",
                        endpoint,
                        attempt + 1,
                        retry_attempts + 1,
                        error,
                    )

                # Check if error is retryable
                if (
                    isinstance(error, APIError)
                    and error.status_code
                    and error.status_code not in Constants.RETRY_STATUS_CODES
                ):
                    # Non-retryable error - fail fast
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

        # All retries exhausted
        metrics.increment("outline.request.exhausted", tags={"endpoint": endpoint})

        raise APIError(
            f"Request failed after {retry_attempts + 1} attempts",
            endpoint=endpoint,
        ) from last_error

    @staticmethod
    def _calculate_delay(attempt: int) -> float:
        """Calculate retry delay with exponential backoff and jitter.

        Jitter prevents thundering herd problem in distributed systems.

        :param attempt: Current attempt number (0-indexed)
        :return: Delay in seconds
        """
        base_delay = Constants.DEFAULT_RETRY_DELAY * (attempt + 1)
        # Secure random jitter: ±20% of base delay
        jitter = base_delay * 0.2 * (secrets.randbelow(40) - 20) / 100
        return max(0.1, base_delay + jitter)


class SSLFingerprintValidator:
    """Enhanced SSL validation with strict fingerprint pinning.

    SECURITY CRITICAL:
    - Outline VPN uses self-signed certificates
    - We disable CA verification but enforce fingerprint pinning
    - Constant-time comparison prevents timing attacks
    - SecretStr keeps fingerprint secure in memory
    - TLS 1.2+ enforcement

    MITM Prevention:
    - Fingerprint verified on every connection
    - Mismatch raises ValueError (connection aborted)
    - Certificate pinning per OWASP recommendations
    """

    __slots__ = ("_expected_fingerprint_secret", "_ssl_context")

    def __init__(self, cert_sha256: SecretStr) -> None:
        """Initialize SSL validator with fingerprint pinning.

        :param cert_sha256: Pre-validated SHA-256 fingerprint as SecretStr

        SECURITY: Fingerprint must be pre-validated by
        Validators.validate_cert_fingerprint() before calling this.
        SecretStr maintained for memory protection.
        """
        self._expected_fingerprint_secret: SecretStr | None = cert_sha256

        # Create SSL context WITHOUT CA verification (self-signed certs)
        # Security is ensured by strict fingerprint pinning
        self._ssl_context: ssl.SSLContext | None = ssl.create_default_context()
        self._ssl_context.check_hostname = False  # We verify via fingerprint
        self._ssl_context.verify_mode = ssl.CERT_NONE  # Accept self-signed

        # SECURITY: Enforce minimum TLS 1.2 (TLS 1.3 preferred if available)
        self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

        # Enable TLS 1.3 if available
        with suppress(AttributeError):
            self._ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Clean up sensitive data on exit."""
        # Clear sensitive references
        self._expected_fingerprint_secret = None
        self._ssl_context = None

    @property
    def ssl_context(self) -> ssl.SSLContext:
        """Get SSL context for aiohttp."""
        if self._ssl_context is None:
            raise RuntimeError("SSL context is no longer available")
        return self._ssl_context

    def _verify_cert_fingerprint(self, cert_der: bytes) -> None:
        """Verify certificate fingerprint matches expected.

        :param cert_der: Certificate in DER format
        :raises ValueError: If fingerprint doesn't match (MITM detected)
        """
        import hashlib

        # Compute actual fingerprint
        actual_fingerprint = hashlib.sha256(cert_der).hexdigest()

        # Get expected fingerprint from secure storage
        if self._expected_fingerprint_secret is None:
            raise RuntimeError("Expected fingerprint is no longer available")
        expected_fingerprint = self._expected_fingerprint_secret.get_secret_value()

        # SECURITY: Constant-time comparison prevents timing attacks
        if not secrets.compare_digest(actual_fingerprint, expected_fingerprint):
            raise ValueError(
                "Certificate fingerprint mismatch - possible MITM attack detected"
            )

    async def verify_connection(
        self,
        session: ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: TraceConnectionCreateEndParams | TraceConnectionReuseconnParams,
    ) -> None:
        """Verify certificate fingerprint during connection.

        :param session: aiohttp session
        :param trace_config_ctx: Trace context
        :param params: Request parameters
        :raises ValueError: If fingerprint doesn't match (MITM detected)
        """
        # Get peer certificate from transport (create/reuse hooks)
        transport = getattr(params, "transport", None)
        if transport is None:
            connection = getattr(params, "connection", None)
            transport = getattr(connection, "transport", None) if connection else None
        if transport is None:
            return

        ssl_object = transport.get_extra_info("ssl_object")
        if ssl_object is None:
            return

        # Get certificate in DER format (binary)
        cert_der = ssl_object.getpeercert(binary_form=True)
        if cert_der:
            # SECURITY: Verify fingerprint (raises on mismatch)
            self._verify_cert_fingerprint(cert_der)


class BaseHTTPClient:
    """HTTP client with comprehensive security features."""

    __slots__ = (
        "_active_requests",
        "_active_requests_lock",
        "_allow_private_networks",
        "_api_hostname",
        "_api_url",
        "_audit_logger",
        "_cert_sha256",
        "_circuit_breaker",
        "_enable_logging",
        "_max_connections",
        "_metrics",
        "_rate_limiter",
        "_rate_limiter_tps",
        "_resolve_dns_for_ssrf",
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
        allow_private_networks: bool = True,
        resolve_dns_for_ssrf: bool = False,
        audit_logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        """Initialize base HTTP client with enhanced security.

        :param api_url: Outline server API URL
        :param cert_sha256: SHA-256 certificate fingerprint (as SecretStr)
        :param timeout: Request timeout in seconds
        :param retry_attempts: Number of retry attempts
        :param max_connections: Connection pool size
        :param user_agent: Custom user agent string
        :param enable_logging: Enable debug logging
        :param circuit_config: Circuit breaker configuration
        :param rate_limit: Maximum concurrent requests
        :param allow_private_networks: Allow private/local network api_url
        :param resolve_dns_for_ssrf: Resolve DNS for SSRF checks (strict mode)
        :param audit_logger: Custom audit logger
        :param metrics: Custom metrics collector
        :raises ValueError: If parameters are invalid
        """
        # Validate and sanitize URL (removes trailing slash)
        self._api_url = Validators.validate_url(
            api_url,
            allow_private_networks=allow_private_networks,
            resolve_dns=False,
        ).rstrip("/")
        self._api_hostname = urlparse(self._api_url).hostname
        self._allow_private_networks = allow_private_networks
        self._resolve_dns_for_ssrf = resolve_dns_for_ssrf

        # SECURITY: Validate fingerprint and keep as SecretStr
        # Never expose as plain string - SecretStr protects memory
        self._cert_sha256 = Validators.validate_cert_fingerprint(cert_sha256)

        # Validate numeric parameters
        self._validate_numeric_params(timeout, retry_attempts, max_connections)

        self._timeout = aiohttp.ClientTimeout(total=float(timeout))
        self._retry_attempts = retry_attempts
        self._max_connections = max_connections
        self._user_agent = user_agent or Constants.DEFAULT_USER_AGENT
        self._enable_logging = enable_logging

        # SECURITY: Pass SecretStr directly - maintains security
        self._ssl_validator = SSLFingerprintValidator(self._cert_sha256)

        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self._circuit_breaker: CircuitBreaker | None = None

        if circuit_config is not None:
            self._init_circuit_breaker(circuit_config)

        # Rate limiting: concurrent + token bucket
        self._rate_limiter = RateLimiter(rate_limit)
        self._rate_limiter_tps = TokenBucketRateLimiter()

        # Audit logging and metrics
        self._audit_logger = audit_logger or NoOpAuditLogger()
        self._metrics = metrics or NoOpMetrics()
        self._retry_helper = RetryHelper()

        # Active request tracking for graceful shutdown
        self._active_requests: set[asyncio.Task[ResponseData]] = set()
        self._active_requests_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    @staticmethod
    def _validate_numeric_params(
        timeout: int, retry_attempts: int, max_connections: int
    ) -> None:
        """Validate numeric parameters.

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

        Ensures circuit breaker timeout accounts for retries.

        :param config: Circuit breaker configuration
        """
        from .circuit_breaker import CircuitBreaker, CircuitConfig

        # Calculate maximum possible request time including retries
        total_timeout = self._timeout.total or 0.0
        max_retry_time = total_timeout * (self._retry_attempts + 1)
        max_delays = sum(
            Constants.DEFAULT_RETRY_DELAY * (i + 1) for i in range(self._retry_attempts)
        )
        cb_timeout = max_retry_time + max_delays + 5.0  # +5s safety margin

        # Adjust circuit breaker timeout if too low
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
        """Ensure aiohttp session is initialized with enhanced security.

        Double-checked locking pattern for thread-safe lazy initialization.
        """
        if self._session is not None and not self._session.closed:
            return  # Fast path - no lock needed

        async with self._session_lock:
            # Double-check after acquiring lock
            if self._session is not None and not self._session.closed:
                return

            # Create connector with security and performance settings
            connector = aiohttp.TCPConnector(
                ssl=self._ssl_validator.ssl_context,
                limit=self._max_connections,
                limit_per_host=max(1, self._max_connections // 2),
                ttl_dns_cache=Constants.DNS_CACHE_TTL,
                enable_cleanup_closed=True,
                force_close=False,  # Reuse connections for performance
            )

            # Verifies certificate on every request (MITM prevention)
            trace_config = aiohttp.TraceConfig()
            trace_config.on_connection_create_end.append(
                self._ssl_validator.verify_connection
            )
            trace_config.on_connection_reuseconn.append(
                self._ssl_validator.verify_connection
            )

            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
                raise_for_status=False,  # Manual status handling
                trace_configs=[trace_config],
            )

            if logger.isEnabledFor(Constants.LOG_LEVEL_DEBUG):
                logger.debug("HTTP session initialized")

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: JsonPayload = None,
        params: QueryParams | None = None,
    ) -> ResponseData:
        """Make HTTP request with comprehensive protection.

        Request flow:
        1. Ensure session initialized
        2. Generate secure correlation ID
        3. Apply token bucket rate limiting
        4. Apply circuit breaker (if configured)
        5. Execute request with retry logic
        6. Track metrics and audit log

        :param method: HTTP method (GET, POST, PUT, DELETE)
        :param endpoint: API endpoint path
        :param json: JSON payload for request body
        :param params: Query parameters
        :return: Response data as dict
        :raises APIError: If request fails after retries
        :raises CircuitOpenError: If circuit breaker is open
        :raises TimeoutError: If request times out
        :raises ConnectionError: If connection fails
        """
        # Strict SSRF re-check at request time (DNS rebinding protection)
        if (
            self._resolve_dns_for_ssrf
            and not self._allow_private_networks
            and self._api_hostname
            and SSRFProtection.is_blocked_hostname_uncached(self._api_hostname)
        ):
            raise ValueError(
                f"Access to {self._api_hostname} is blocked (SSRF protection)"
            )

        await self._ensure_session()

        # SECURITY: Generate secure correlation ID for distributed tracing
        request_id = SecureIDGenerator.generate_correlation_id()
        correlation_id.set(request_id)

        # Apply token bucket rate limiting (requests per second)
        await self._rate_limiter_tps.acquire()

        # Circuit breaker protection (if configured)
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
                # Track circuit breaker open event
                self._metrics.increment(
                    "outline.circuit.open",
                    tags={"endpoint": endpoint, "method": method},
                )
                if logger.isEnabledFor(Constants.LOG_LEVEL_ERROR):
                    logger.error(
                        "Circuit breaker OPEN for %s - rejecting request", endpoint
                    )
                raise

        # No circuit breaker - direct execution
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
        """Inner request method with comprehensive error handling.

        Implements retry logic, metrics, audit logging, and error handling.

        :param method: HTTP method
        :param endpoint: API endpoint
        :param json: JSON payload
        :param params: Query parameters
        :param correlation_id: Request correlation ID
        :return: Response data
        """

        async def _make_request() -> ResponseData:
            """Actual request execution (closure for retry logic)."""
            await self._ensure_session()

            url = self._build_url(endpoint)
            start_time = time.monotonic()

            # Track active request for graceful shutdown
            current_task = asyncio.current_task()
            if current_task:
                async with self._active_requests_lock:
                    self._active_requests.add(current_task)

            try:
                # Apply concurrent rate limiting
                async with self._rate_limiter:
                    # SECURITY: Headers with security and tracing info
                    headers = {
                        "User-Agent": self._user_agent,
                        "X-Request-ID": correlation_id,
                        "X-Content-Type-Options": "nosniff",  # Security header
                        "X-Frame-Options": "DENY",  # Security header
                        "Accept": "application/json",
                    }

                    if self._session is None:
                        raise APIError(
                            "HTTP session not initialized", endpoint=endpoint
                        )

                    async with self._session.request(
                        method, url, json=json, params=params, headers=headers
                    ) as response:
                        duration = time.monotonic() - start_time

                        # Debug logging (if enabled)
                        if self._enable_logging and logger.isEnabledFor(
                            Constants.LOG_LEVEL_DEBUG
                        ):
                            safe_endpoint = Validators.sanitize_endpoint_for_logging(
                                endpoint
                            )
                            logger.debug(
                                "[%s] %s %s -> %d",
                                correlation_id,
                                method,
                                safe_endpoint,
                                response.status,
                                extra={"correlation_id": correlation_id},
                            )

                        # Metrics: request duration
                        self._metrics.timing(
                            "outline.request.duration",
                            duration,
                            tags={"method": method, "endpoint": endpoint},
                        )

                        # Handle HTTP errors (4xx, 5xx)
                        if response.status >= 400:
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

                        # Metrics: successful request
                        self._metrics.increment(
                            "outline.request.success",
                            tags={"method": method, "endpoint": endpoint},
                        )

                        # Handle 204 No Content
                        if response.status == 204:
                            return {"success": True}

                        # Parse JSON response with size limits
                        return await self._parse_response_safe(response, endpoint)

            except asyncio.TimeoutError as e:
                duration = time.monotonic() - start_time

                # Track timeout metrics
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
                # Track connection errors
                self._metrics.increment(
                    "outline.connection.error",
                    tags={
                        "endpoint": endpoint,
                        "error_type": type(e).__name__,
                        "method": method,
                    },
                )

                # SECURITY: Sanitize hostname and error message
                hostname = Validators.sanitize_url_for_logging(url)
                safe_message = CredentialSanitizer.sanitize(str(e))

                raise OutlineConnectionError(
                    f"Failed to connect: {safe_message}",
                    host=hostname,
                ) from e

            except aiohttp.ClientError as e:
                # Track client errors
                self._metrics.increment(
                    "outline.request.client_error",
                    tags={
                        "endpoint": endpoint,
                        "error_type": type(e).__name__,
                        "method": method,
                    },
                )

                # SECURITY: Sanitize error message
                safe_message = CredentialSanitizer.sanitize(str(e))

                raise APIError(
                    f"Request failed: {safe_message}", endpoint=endpoint
                ) from e

            finally:
                # Remove from active requests
                if current_task:
                    async with self._active_requests_lock:
                        self._active_requests.discard(current_task)

        # Execute with retry logic
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
        # Check Content-Length header
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                length_value = int(content_length)
            except ValueError:
                length_value = None

            if length_value is not None and length_value > Constants.MAX_RESPONSE_SIZE:
                raise APIError(
                    f"Response too large: {length_value} bytes "
                    f"(max {Constants.MAX_RESPONSE_SIZE})",
                    status_code=response.status,
                    endpoint=endpoint,
                )

        # Validate Content-Type
        content_type = response.headers.get("Content-Type", "").lower()
        if (
            content_type
            and "application/json" not in content_type
            and logger.isEnabledFor(Constants.LOG_LEVEL_WARNING)
        ):
            logger.warning("Unexpected Content-Type: %s", content_type)

        # Read response in chunks with size limit
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

        # Parse JSON
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return cast(ResponseData, parsed)
            if 200 <= response.status < 300:
                return {"success": True}
            raise APIError(
                f"Expected JSON object from {endpoint}, got {type(parsed).__name__}",
                status_code=response.status,
                endpoint=endpoint,
            )
        except (json.JSONDecodeError, ValueError) as e:
            # Success status but invalid JSON - return generic success
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

        # SECURITY: Sanitize error message
        safe_message = CredentialSanitizer.sanitize(message)

        raise APIError(safe_message, status_code=response.status, endpoint=endpoint)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Graceful shutdown with timeout.

        Waits for active requests to complete before closing session.

        :param timeout: Maximum time to wait for active requests (seconds)
        """
        if self._shutdown_event.is_set():
            return  # Already shutting down

        self._shutdown_event.set()

        # Get snapshot of active requests
        async with self._active_requests_lock:
            active_requests = list(self._active_requests)

        if active_requests:
            if logger.isEnabledFor(Constants.LOG_LEVEL_INFO):
                logger.info("Waiting for %d active requests...", len(active_requests))

            try:
                # Wait for active requests with timeout
                await asyncio.wait_for(
                    asyncio.gather(*active_requests, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                    logger.warning(
                        "Shutdown timeout, cancelling %d requests",
                        len(active_requests),
                    )
                # Force cancel remaining requests
                for task in active_requests:
                    if not task.done():
                        task.cancel()

        # Close session
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

        if logger.isEnabledFor(Constants.LOG_LEVEL_DEBUG):
            logger.debug("HTTP client shutdown complete")

    # ===== Properties =====

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
        """Get current concurrent rate limit."""
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
        """Change concurrent rate limit dynamically."""
        await self._rate_limiter.set_limit(new_limit)

    def get_rate_limiter_stats(self) -> dict[str, int | float]:
        """Get comprehensive rate limiter statistics.

        Includes both concurrent and token bucket metrics.

        :return: Rate limiter statistics
        """
        return {
            "limit": self._rate_limiter.limit,
            "active": len(self._active_requests),
            "available": self._rate_limiter.available,
            "tokens_available": self._rate_limiter_tps.available_tokens,
        }

    async def reset_circuit_breaker(self) -> bool:
        """Reset circuit breaker to closed state.

        :return: True if circuit breaker was reset, False if not configured
        """
        if self._circuit_breaker:
            await self._circuit_breaker.reset()
            return True
        return False

    def get_circuit_metrics(self) -> dict[str, int | float | str] | None:
        """Get circuit breaker metrics.

        :return: Circuit breaker metrics or None if not configured
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


__all__ = ["BaseHTTPClient", "MetricsCollector", "NoOpMetrics", "correlation_id"]
