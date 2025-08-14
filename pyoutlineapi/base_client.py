"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

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
from functools import wraps
from typing import Any, Callable, Final, Set, Awaitable, TypeVar, ParamSpec, Protocol
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientResponse, Fingerprint
from pydantic import BaseModel

from .circuit_breaker import CircuitConfig, AsyncCircuitBreaker
from .common_types import CommonValidators, Constants, mask_sensitive_data
from .exceptions import APIError, OutlineError, CircuitOpenError
from .models import ErrorResponse

# Type variables
P = ParamSpec("P")
T = TypeVar("T")

# Constants
RETRY_STATUS_CODES: Final[Set[int]] = {408, 429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)


# Protocols for better type safety
class HTTPClientProtocol(Protocol):
    """Protocol defining the HTTP client interface."""

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def _get_json_format(self): ...

    async def _parse_response(self, response_data, model: type[BaseModel]): ...

    async def create_access_key(self, param): ...

    async def delete_access_key(self, key_id): ...

    async def rename_access_key(self, key_id, name): ...


def ensure_session(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Decorator to ensure client session is initialized."""

    @wraps(func)
    async def wrapper(self: BaseHTTPClient, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._session or self._session.closed:
            raise RuntimeError("Client session is not initialized or already closed.")
        return await func(self, *args, **kwargs)

    return wrapper


def log_method_call(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Decorator to log method calls with performance metrics."""

    @wraps(func)
    async def wrapper(self: BaseHTTPClient, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._enable_logging:
            return await func(self, *args, **kwargs)

        method_name = func.__name__
        start_time = time.perf_counter()

        # Log method call with masked sensitive data
        safe_kwargs = mask_sensitive_data(kwargs)
        logger.debug(f"Calling {method_name} with args={args[1:]} kwargs={safe_kwargs}")

        try:
            result = await func(self, *args, **kwargs)
            duration = time.perf_counter() - start_time
            logger.debug(f"{method_name} completed in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(f"{method_name} failed after {duration:.3f}s: {e}")
            raise

    return wrapper


class BaseHTTPClient:
    """
    Base HTTP client with circuit breaker integration and proper logging.

    This class provides the core HTTP functionality with proper error handling,
    retry logic, circuit breaker protection, and NON-DUPLICATING logging.
    """

    def __init__(
        self,
        api_url: str,
        cert_sha256: str,
        *,
        timeout: int = Constants.DEFAULT_TIMEOUT,
        retry_attempts: int = Constants.DEFAULT_RETRY_ATTEMPTS,
        enable_logging: bool = False,
        user_agent: str | None = None,
        max_connections: int = Constants.DEFAULT_MAX_CONNECTIONS,
        rate_limit_delay: float = 0.0,
        circuit_breaker_enabled: bool = True,
        circuit_config: CircuitConfig | None = None,
        **kwargs: Any,  # Accept additional kwargs for mixins
    ) -> None:
        # Validate inputs using common validators
        self.__validate_inputs(api_url, cert_sha256)

        # Core configuration
        self._api_url = CommonValidators.validate_url(api_url).rstrip("/")
        self._cert_sha256 = CommonValidators.validate_cert_fingerprint(cert_sha256)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._retry_attempts = retry_attempts
        self._enable_logging = enable_logging
        self._user_agent = user_agent or Constants.DEFAULT_USER_AGENT
        self._max_connections = max_connections
        self._rate_limit_delay = rate_limit_delay

        # Session management
        self._session: aiohttp.ClientSession | None = None
        self._last_request_time: float = 0.0

        # Circuit breaker setup
        self._circuit_breaker_enabled = circuit_breaker_enabled
        self._circuit_breaker: AsyncCircuitBreaker | None = None

        if circuit_breaker_enabled:
            self.__setup_circuit_breaker(circuit_config, timeout)

        # Setup logging ONCE per class, not per instance
        if enable_logging:
            self.__setup_logging()

    @staticmethod
    def __validate_inputs(api_url: str, cert_sha256: str) -> None:
        """Validate constructor inputs (private method)."""
        # Validation is now handled by CommonValidators
        # This method is kept for backward compatibility and additional checks

        if not api_url or not api_url.strip():
            raise ValueError("api_url cannot be empty or whitespace")

        if not cert_sha256 or not cert_sha256.strip():
            raise ValueError("cert_sha256 cannot be empty or whitespace")

    def __setup_circuit_breaker(
        self, circuit_config: CircuitConfig | None, timeout: int
    ) -> None:
        """Setup circuit breaker with configuration (private method)."""
        if circuit_config is None:
            circuit_config = CircuitConfig(
                failure_threshold=5,
                recovery_timeout=60.0,
                success_threshold=3,
                call_timeout=timeout,
                failure_rate_threshold=0.6,
                min_calls_to_evaluate=10,
            )

        self._circuit_breaker = AsyncCircuitBreaker(
            name=f"outline-api-{urlparse(self._api_url).netloc}",
            config=circuit_config,
        )

        if self._enable_logging:
            logger.info(f"Circuit breaker initialized for {self.api_url}")

    @staticmethod
    def __setup_logging() -> None:
        """Setup logging configuration properly without duplication (private method)."""
        # Get the PyOutlineAPI logger (parent of all our loggers)
        pyoutline_logger = logging.getLogger("pyoutlineapi")

        # Only setup if not already configured
        if not pyoutline_logger.handlers and pyoutline_logger.level == logging.NOTSET:
            # Create handler
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)

            # Add handler to the package logger only
            pyoutline_logger.addHandler(handler)
            pyoutline_logger.setLevel(logging.DEBUG)

            # Prevent propagation to root logger to avoid duplication
            pyoutline_logger.propagate = False

            logger.debug("PyOutlineAPI logging configured")

    async def __aenter__(self) -> BaseHTTPClient:
        """Initialize client session and circuit breaker."""
        await self.__initialize_session()

        if self._circuit_breaker:
            await self._circuit_breaker.start()
            if self._enable_logging:
                logger.info(f"Circuit breaker started for {self.api_url}")

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up resources."""
        if self._circuit_breaker:
            await self._circuit_breaker.stop()

        if self._session:
            await self._session.close()
            self._session = None

            if self._enable_logging:
                logger.info("HTTP client session closed")

    async def __initialize_session(self) -> None:
        """Initialize HTTP session (private method)."""
        headers = {"User-Agent": self._user_agent}

        connector = aiohttp.TCPConnector(
            ssl=self.__get_ssl_context(),
            limit=self._max_connections,
            limit_per_host=self._max_connections // 2,
            enable_cleanup_closed=True,
        )

        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            raise_for_status=False,
            connector=connector,
            headers=headers,
        )

        if self._enable_logging:
            logger.info(f"HTTP session initialized for {self.api_url}")

    def __get_ssl_context(self) -> Fingerprint | None:
        """Create SSL fingerprint for certificate validation (private method)."""
        if not self._cert_sha256:
            return None

        try:
            return Fingerprint(binascii.unhexlify(self._cert_sha256))
        except binascii.Error as e:
            raise ValueError(f"Invalid certificate SHA256: {self._cert_sha256}") from e
        except Exception as e:
            raise OutlineError("Failed to create SSL context") from e

    async def __apply_rate_limiting(self) -> None:
        """Apply rate limiting if configured (private method)."""
        if self._rate_limit_delay <= 0:
            return

        time_since_last = time.time() - self._last_request_time
        if time_since_last < self._rate_limit_delay:
            delay = self._rate_limit_delay - time_since_last
            await asyncio.sleep(delay)

        self._last_request_time = time.time()

    @ensure_session
    @log_method_call
    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request with circuit breaker protection.

        This is the main public method for making HTTP requests.

        Args:
            method: HTTP method
            endpoint: API endpoint
            json: JSON data for request body
            params: Query parameters

        Returns:
            Parsed JSON response data

        Raises:
            APIError: If request fails
            CircuitOpenError: If circuit breaker is open
        """
        if self._circuit_breaker_enabled and self._circuit_breaker:
            try:
                return await self._circuit_breaker.call(
                    self.__make_request, method, endpoint, json=json, params=params
                )
            except CircuitOpenError as e:
                logger.warning(
                    f"Circuit breaker OPEN for {endpoint}. Retry after {e.retry_after:.1f}s"
                )
                raise APIError(
                    f"Service temporarily unavailable. Retry after {e.retry_after:.1f} seconds",
                    status_code=503,
                ) from e
        else:
            return await self.__make_request(method, endpoint, json=json, params=params)

    async def __make_request(
        self,
        method: str,
        endpoint: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Internal method to execute HTTP request (private method)."""
        await self.__apply_rate_limiting()
        url = self.__build_url(endpoint)

        async def _do_request() -> dict[str, Any]:
            if self._enable_logging:
                safe_url = url.split("?")[0] if "?" in url else url
                logger.debug(f"Making {method} request to {safe_url}")

            async with self._session.request(
                method,
                url,
                json=json,
                params=params,
                raise_for_status=False,
            ) as response:
                if self._enable_logging:
                    logger.debug(f"Response: {response.status} {response.reason}")

                if response.status >= 400:
                    await self.__handle_error_response(response)

                # Parse response data
                if response.status == 204:
                    return {"success": True}

                try:
                    return await response.json()
                except aiohttp.ContentTypeError:
                    # For non-JSON responses, return success indicator
                    return {"success": True}

        return await self.__retry_request(_do_request)

    async def __retry_request(
        self,
        request_func: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Execute request with retry logic (private method)."""
        last_error = None

        for attempt in range(self._retry_attempts):
            try:
                return await request_func()
            except (aiohttp.ClientError, APIError) as error:
                last_error = error

                # Don't retry if it's not a retriable error
                if isinstance(error, APIError) and (
                    error.status_code not in RETRY_STATUS_CODES
                ):
                    raise

                # Don't sleep on the last attempt
                if attempt < self._retry_attempts - 1:
                    delay = Constants.DEFAULT_RETRY_DELAY * (attempt + 1)
                    await asyncio.sleep(delay)

        raise APIError(
            f"Request failed after {self._retry_attempts} attempts: {last_error}",
            getattr(last_error, "status_code", None),
        )

    def __build_url(self, endpoint: str) -> str:
        """Build full URL for the API endpoint (private method)."""
        if not isinstance(endpoint, str):
            raise ValueError("Endpoint must be a string")

        url = f"{self._api_url}/{endpoint.lstrip('/')}"

        # Validate the final URL
        try:
            CommonValidators.validate_url(url)
        except ValueError as e:
            raise ValueError(f"Invalid URL constructed: {url}") from e

        return url

    @staticmethod
    async def __handle_error_response(response: ClientResponse) -> None:
        """Handle error responses from the API (private method)."""
        try:
            error_data = await response.json()
            error = ErrorResponse.model_validate(error_data)
            raise APIError(f"{error.code}: {error.message}", response.status)
        except (ValueError, aiohttp.ContentTypeError):
            raise APIError(
                f"HTTP {response.status}: {response.reason}", response.status
            )

    # Public circuit breaker management methods

    @property
    def circuit_breaker_enabled(self) -> bool:
        """Check if circuit breaker is enabled."""
        return self._circuit_breaker_enabled and self._circuit_breaker is not None

    @property
    def circuit_state(self) -> str | None:
        """Get current circuit breaker state."""
        return self._circuit_breaker.state.name if self._circuit_breaker else None

    async def get_circuit_breaker_status(self) -> dict[str, Any]:
        """Get comprehensive circuit breaker status."""
        if not self._circuit_breaker:
            return {"enabled": False, "message": "Circuit breaker not enabled"}

        metrics = self._circuit_breaker.metrics

        return {
            "enabled": True,
            "name": self._circuit_breaker.name,
            "state": self._circuit_breaker.state.name,
            "metrics": {
                "total_calls": metrics.total_calls,
                "successful_calls": metrics.successful_calls,
                "failed_calls": metrics.failed_calls,
                "short_circuited_calls": metrics.short_circuited_calls,
                "success_rate": metrics.success_rate,
                "failure_rate": metrics.failure_rate,
                "avg_response_time": metrics.avg_response_time,
                "state_changes": metrics.state_changes,
                "last_state_change": metrics.last_state_change,
                "time_in_open_state": metrics.time_in_open_state,
            },
            "config": {
                "failure_threshold": self._circuit_breaker.config.failure_threshold,
                "recovery_timeout": self._circuit_breaker.config.recovery_timeout,
                "success_threshold": self._circuit_breaker.config.success_threshold,
                "failure_rate_threshold": self._circuit_breaker.config.failure_rate_threshold,
            },
        }

    async def reset_circuit_breaker(self) -> bool:
        """Manually reset circuit breaker."""
        if not self._circuit_breaker:
            return False

        await self._circuit_breaker.reset()
        if self._enable_logging:
            logger.info("Circuit breaker manually reset")
        return True

    async def force_circuit_open(self) -> bool:
        """Manually force circuit breaker to OPEN state."""
        if not self._circuit_breaker:
            return False

        await self._circuit_breaker.force_open()
        if self._enable_logging:
            logger.warning("Circuit breaker manually opened")
        return True

    # Public properties

    @property
    def api_url(self) -> str:
        """Get the API URL (without sensitive parts)."""
        parsed = urlparse(self._api_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def session(self) -> aiohttp.ClientSession | None:
        """Access the current client session."""
        return self._session

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._session is not None and not self._session.closed

    def __repr__(self) -> str:
        """String representation."""
        status = "connected" if self.is_connected else "disconnected"
        cb_status = f", circuit={self.circuit_state}" if self._circuit_breaker else ""

        return (
            f"{self.__class__.__name__}("
            f"url={self.api_url}, "
            f"status={status}"
            f"{cb_status})"
        )
