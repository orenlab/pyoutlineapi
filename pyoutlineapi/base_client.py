"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Base HTTP client with lazy feature loading.
"""

from __future__ import annotations

import asyncio
import binascii
import logging
from asyncio import Semaphore
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientResponse, Fingerprint

from .common_types import Constants, Validators
from .exceptions import (
    APIError,
    CircuitOpenError,
)
from .exceptions import (
    ConnectionError as OutlineConnectionError,
)
from .exceptions import (
    TimeoutError as OutlineTimeoutError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic import SecretStr

    from .circuit_breaker import CircuitBreaker, CircuitConfig

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

# Retryable HTTP status codes
RETRY_CODES = frozenset({408, 429, 500, 502, 503, 504})


class RateLimiter:
    """
    Rate limiter with dynamic limit adjustment.

    Wraps asyncio.Semaphore to provide better control and monitoring
    of concurrent operations.
    """

    __slots__ = ("_semaphore", "_limit", "_lock")

    def __init__(self, limit: int) -> None:
        """
        Initialize rate limiter.

        Args:
            limit: Maximum concurrent operations

        Example:
            >>> limiter = RateLimiter(limit=100)
            >>> async with limiter:
            ...     # Protected operation
            ...     await some_async_operation()
        """
        self._limit = limit
        self._semaphore = Semaphore(limit)
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> RateLimiter:
        """Acquire semaphore."""
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Release semaphore."""
        self._semaphore.release()

    @property
    def limit(self) -> int:
        """
        Get current rate limit.

        Returns:
            int: Maximum concurrent operations allowed
        """
        return self._limit

    @property
    def available(self) -> int:
        """
        Get number of available slots.

        Returns:
            int: Number of additional operations that can be started
        """
        # Semaphore._value is internal but widely used
        return getattr(self._semaphore, "_value", 0)

    @property
    def active(self) -> int:
        """
        Get number of active operations.

        Returns:
            int: Number of operations currently being processed
        """
        return self._limit - self.available

    async def set_limit(self, new_limit: int) -> None:
        """
        Change rate limit dynamically.

        Args:
            new_limit: New maximum concurrent operations

        Raises:
            ValueError: If new_limit < 1

        Note:
            This recreates the semaphore. Current operations continue,
            but new operations will use the new limit.

        Example:
            >>> limiter = RateLimiter(limit=50)
            >>> await limiter.set_limit(100)  # Increase to 100
        """
        if new_limit < 1:
            raise ValueError("Rate limit must be at least 1")

        async with self._lock:
            old_limit = self._limit
            self._limit = new_limit

            # Recreate semaphore with new limit
            # Note: This is safe because we hold the lock
            self._semaphore = Semaphore(new_limit)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Rate limit changed: {old_limit} -> {new_limit}")


def _ensure_session(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """
    Ensure session is initialized before operation.

    Decorator for methods that require an active HTTP session.
    """

    @wraps(func)
    async def wrapper(self: BaseHTTPClient, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._session or self._session.closed:
            raise RuntimeError("Client session not initialized")
        return await func(self, *args, **kwargs)

    return wrapper


class BaseHTTPClient:
    """
    Base HTTP client with optional circuit breaker.

    Features:
    - Lazy loading of circuit breaker (only if enabled)
    - Clean retry logic
    - Proper error handling
    - SSL certificate validation
    - Rate limiting protection

    This is the foundation for AsyncOutlineClient and provides
    low-level HTTP operations with resilience features.
    """

    __slots__ = (
        "_api_url",
        "_cert_sha256",
        "_timeout",
        "_retry_attempts",
        "_max_connections",
        "_user_agent",
        "_session",
        "_circuit_breaker",
        "_enable_logging",
        "_rate_limiter",
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
    ) -> None:
        """
        Initialize base HTTP client.

        Args:
            api_url: API URL with secret path
            cert_sha256: Certificate fingerprint (protected with SecretStr)
            timeout: Request timeout in seconds (default: 30)
            retry_attempts: Number of retry attempts (default: 3)
            max_connections: Maximum connection pool size (default: 10)
            user_agent: Custom user agent string
            enable_logging: Enable debug logging
            circuit_config: Circuit breaker configuration
            rate_limit: Maximum concurrent requests (default: 100)
        """
        # Validate inputs
        self._api_url = Validators.validate_url(api_url).rstrip("/")
        self._cert_sha256 = Validators.validate_cert_fingerprint(cert_sha256)

        # Configuration
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._retry_attempts = retry_attempts
        self._max_connections = max_connections
        self._user_agent = user_agent or Constants.DEFAULT_USER_AGENT
        self._enable_logging = enable_logging

        # Session (initialized on enter)
        self._session: aiohttp.ClientSession | None = None

        # Lazy load circuit breaker
        self._circuit_breaker: CircuitBreaker | None = None
        if circuit_config is not None:
            self._init_circuit_breaker(circuit_config)

        # Rate limiting
        self._rate_limiter = RateLimiter(rate_limit)

    def _init_circuit_breaker(self, config: CircuitConfig) -> None:
        """Lazy initialization of circuit breaker."""
        from .circuit_breaker import CircuitBreaker, CircuitConfig

        # Calculate proper timeout for circuit breaker
        # It should be enough for all retries: timeout * (attempts + 1) + delays
        # Formula: timeout * (retry_attempts + 1) + sum(delays) + buffer
        max_retry_time = self._timeout.total * (self._retry_attempts + 1)
        max_delays = sum(
            Constants.DEFAULT_RETRY_DELAY * i
            for i in range(1, self._retry_attempts + 1)
        )
        cb_timeout = max_retry_time + max_delays + 5.0  # +5s buffer (reduced from 10s)

        # Override call_timeout if needed
        if config.call_timeout < cb_timeout:
            if self._enable_logging:
                logger.info(
                    f"Adjusting circuit breaker timeout from {config.call_timeout}s "
                    f"to {cb_timeout}s to accommodate retries"
                )
            # Create new config with adjusted timeout
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

        if self._enable_logging:
            logger.info(
                f"Circuit breaker initialized: "
                f"failure_threshold={config.failure_threshold}, "
                f"call_timeout={config.call_timeout:.1f}s"
            )

    async def __aenter__(self) -> BaseHTTPClient:
        """
        Initialize session on enter.

        Example:
            >>> async with BaseHTTPClient(...) as client:
            ...     # Session is ready
            ...     await client._request("GET", "server")
        """
        await self._init_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up on exit."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _init_session(self) -> None:
        """Initialize HTTP session with SSL configuration."""
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
        """
        Create SSL fingerprint for certificate validation.

        Returns:
            Fingerprint: SSL fingerprint object

        Raises:
            ValueError: If certificate format is invalid
        """
        try:
            return Fingerprint(binascii.unhexlify(self._cert_sha256.get_secret_value()))
        except binascii.Error as e:
            raise ValueError(
                "Invalid certificate fingerprint format. "
                "Expected 64 hexadecimal characters (SHA-256)."
            ) from e

    @_ensure_session
    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request with optional circuit breaker protection and rate limiting.

        This is an INTERNAL method. Use high-level API methods instead
        (get_server_info, create_access_key, etc.)

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            json: JSON request body
            params: Query parameters

        Returns:
            dict: Response data

        Raises:
            APIError: If request fails
            CircuitOpenError: If circuit breaker is open
            TimeoutError: If request times out
            ConnectionError: If connection fails
        """
        # Rate limiting protection
        async with self._rate_limiter:
            # Use circuit breaker if available
            if self._circuit_breaker:
                try:
                    return await self._circuit_breaker.call(
                        self._do_request,
                        method,
                        endpoint,
                        json=json,
                        params=params,
                    )
                except CircuitOpenError:
                    if self._enable_logging:
                        logger.warning(f"Circuit open for {endpoint}")
                    raise

            # Direct call without circuit breaker
            return await self._do_request(method, endpoint, json=json, params=params)

    async def _do_request(
        self,
        method: str,
        endpoint: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute HTTP request with retries and proper error handling."""
        url = self._build_url(endpoint)

        async def _make_request() -> dict[str, Any]:
            try:
                async with self._session.request(
                    method,
                    url,
                    json=json,
                    params=params,
                ) as response:
                    if self._enable_logging:
                        logger.debug(f"{method} {endpoint} -> {response.status}")

                    if response.status >= 400:
                        await self._handle_error(response, endpoint)

                    # Handle 204 No Content
                    if response.status == 204:
                        return {"success": True}

                    # Parse JSON
                    try:
                        return await response.json()
                    except aiohttp.ContentTypeError:
                        return {"success": True}

            except asyncio.TimeoutError as e:
                # Convert asyncio.TimeoutError to our TimeoutError
                raise OutlineTimeoutError(
                    f"Request to {endpoint} timed out",
                    timeout=self._timeout.total,
                ) from e

            except aiohttp.ClientConnectionError as e:
                # Connection errors (refused, reset, etc.)
                raise OutlineConnectionError(
                    f"Failed to connect to server: {e}",
                    host=urlparse(url).netloc,
                ) from e

            except aiohttp.ServerDisconnectedError as e:
                # Server disconnected
                raise OutlineConnectionError(
                    f"Server disconnected: {e}",
                    host=urlparse(url).netloc,
                ) from e

            except aiohttp.ClientError as e:
                # Other aiohttp errors
                raise APIError(
                    f"Request failed: {e}",
                    endpoint=endpoint,
                ) from e

        # Retry logic
        return await self._retry_request(_make_request, endpoint)

    async def _retry_request(
        self,
        request_func: Callable[[], Awaitable[dict[str, Any]]],
        endpoint: str,
    ) -> dict[str, Any]:
        """
        Execute request with retry logic.

        Note: retry_attempts represents the number of RETRY attempts, not total attempts.
        Total attempts = retry_attempts + 1 (initial attempt + retries).
        """
        last_error = None

        for attempt in range(self._retry_attempts + 1):
            try:
                return await request_func()

            except (
                OutlineTimeoutError,
                OutlineConnectionError,
                APIError,
            ) as error:
                last_error = error

                # Log the error
                if self._enable_logging:
                    logger.warning(
                        f"Request to {endpoint} failed (attempt {attempt + 1}/{self._retry_attempts + 1}): {error}"
                    )

                # Don't retry non-retryable errors
                if isinstance(error, APIError) and error.status_code not in RETRY_CODES:
                    raise

                # Don't sleep on last attempt
                if attempt < self._retry_attempts:
                    delay = Constants.DEFAULT_RETRY_DELAY * (attempt + 1)
                    if self._enable_logging:
                        logger.debug(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)

        # All retries failed
        if self._enable_logging:
            logger.error(
                f"All {self._retry_attempts + 1} attempts failed for {endpoint}"
            )

        raise APIError(
            f"Request failed after {self._retry_attempts + 1} attempts",
            endpoint=endpoint,
        ) from last_error

    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL for endpoint.

        Args:
            endpoint: API endpoint path

        Returns:
            str: Complete URL
        """
        return f"{self._api_url}/{endpoint.lstrip('/')}"

    @staticmethod
    async def _handle_error(response: ClientResponse, endpoint: str) -> None:
        """Handle error responses."""
        try:
            error_data = await response.json()
            message = error_data.get("message", response.reason)
        except (ValueError, aiohttp.ContentTypeError):
            message = response.reason

        raise APIError(
            message,
            status_code=response.status,
            endpoint=endpoint,
        )

    # ===== Properties =====

    @property
    def api_url(self) -> str:
        """
        Get sanitized API URL (without secret path).

        Returns:
            str: URL with only scheme://netloc

        Example:
            >>> client.api_url
            'https://server.com:12345'
        """
        parsed = urlparse(self._api_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def is_connected(self) -> bool:
        """
        Check if session is active.

        Returns:
            bool: True if session exists and is not closed
        """
        return self._session is not None and not self._session.closed

    @property
    def circuit_state(self) -> str | None:
        """
        Get circuit breaker state.

        Returns:
            str | None: State name (CLOSED, OPEN, HALF_OPEN) or None if disabled
        """
        if self._circuit_breaker:
            return self._circuit_breaker.state.name
        return None

    @property
    def rate_limit(self) -> int:
        """
        Get current rate limit.

        Returns:
            int: Maximum concurrent requests allowed
        """
        return self._rate_limiter.limit

    @property
    def active_requests(self) -> int:
        """
        Get number of currently active requests.

        Returns:
            int: Number of requests currently being processed
        """
        return self._rate_limiter.active

    @property
    def available_slots(self) -> int:
        """
        Get number of available request slots.

        Returns:
            int: Number of additional requests that can be started
        """
        return self._rate_limiter.available

    # ===== Rate Limiter Management =====

    async def set_rate_limit(self, new_limit: int) -> None:
        """
        Change rate limit dynamically.

        Args:
            new_limit: New maximum concurrent requests

        Raises:
            ValueError: If new_limit < 1

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     await client.set_rate_limit(200)  # Increase to 200
            ...     print(f"New limit: {client.rate_limit}")
        """
        await self._rate_limiter.set_limit(new_limit)

    def get_rate_limiter_stats(self) -> dict[str, int]:
        """
        Get rate limiter statistics.

        Returns:
            dict: Dictionary with rate limiter stats (limit, active, available)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     stats = client.get_rate_limiter_stats()
            ...     print(f"Active: {stats['active']}/{stats['limit']}")
        """
        return {
            "limit": self._rate_limiter.limit,
            "active": self._rate_limiter.active,
            "available": self._rate_limiter.available,
        }

    # ===== Circuit Breaker Management =====

    async def reset_circuit_breaker(self) -> bool:
        """
        Manually reset circuit breaker to closed state.

        Returns:
            bool: True if circuit breaker exists and was reset, False otherwise

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     if await client.reset_circuit_breaker():
            ...         print("Circuit breaker reset")
        """
        if self._circuit_breaker:
            await self._circuit_breaker.reset()
            return True
        return False

    def get_circuit_metrics(self) -> dict[str, Any] | None:
        """
        Get circuit breaker metrics.

        Returns:
            dict | None: Circuit breaker metrics or None if disabled

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     metrics = client.get_circuit_metrics()
            ...     if metrics:
            ...         print(f"State: {metrics['state']}")
            ...         print(f"Success rate: {metrics['success_rate']:.2%}")
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
]
