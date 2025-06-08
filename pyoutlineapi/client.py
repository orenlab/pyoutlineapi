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
from contextlib import asynccontextmanager
from functools import wraps
from typing import (
    Any,
    AsyncGenerator,
    Literal,
    TypeAlias,
    Union,
    overload,
    Optional,
    ParamSpec,
    TypeVar,
    Callable,
    Final,
    Set,
    Awaitable,
)
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientResponse, Fingerprint
from pydantic import BaseModel

from .exceptions import APIError, OutlineError
from .models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    AccessKeyNameRequest,
    DataLimit,
    DataLimitRequest,
    ErrorResponse,
    ExperimentalMetrics,
    HostnameRequest,
    MetricsEnabledRequest,
    MetricsStatusResponse,
    PortRequest,
    Server,
    ServerMetrics,
    ServerNameRequest,
)

# Type variables for decorator
P = ParamSpec("P")
T = TypeVar("T")

# Type aliases
JsonDict: TypeAlias = dict[str, Any]
ResponseType = Union[JsonDict, BaseModel]

# Constants
MIN_PORT: Final[int] = 1025
MAX_PORT: Final[int] = 65535
DEFAULT_RETRY_ATTEMPTS: Final[int] = 3
DEFAULT_RETRY_DELAY: Final[float] = 1.0
RETRY_STATUS_CODES: Final[Set[int]] = {408, 429, 500, 502, 503, 504}

# Setup logger
logger = logging.getLogger(__name__)


def ensure_context(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to ensure client session is initialized."""

    @wraps(func)
    async def wrapper(self: AsyncOutlineClient, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._session or self._session.closed:
            raise RuntimeError("Client session is not initialized or already closed.")
        return await func(self, *args, **kwargs)

    return wrapper


def log_method_call(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to log method calls with performance metrics."""

    @wraps(func)
    async def wrapper(self: AsyncOutlineClient, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._enable_logging:
            return await func(self, *args, **kwargs)

        method_name = func.__name__
        start_time = time.perf_counter()

        # Log method call (excluding sensitive data)
        safe_kwargs = {k: v for k, v in kwargs.items() if k not in {'password', 'cert_sha256'}}
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


class AsyncOutlineClient:
    """
    Asynchronous client for the Outline VPN Server API.

    Args:
        api_url: Base URL for the Outline server API
        cert_sha256: SHA-256 fingerprint of the server's TLS certificate
        json_format: Return raw JSON instead of Pydantic models
        timeout: Request timeout in seconds
        retry_attempts: Number of retry attempts connecting to the API
        enable_logging: Enable debug logging for API calls
        user_agent: Custom user agent string
        max_connections: Maximum number of connections in the pool
        rate_limit_delay: Minimum delay between requests (seconds)

    Examples:
        >>> async def main():
        ...     async with AsyncOutlineClient(
        ...         "https://example.com:1234/secret",
        ...         "ab12cd34...",
        ...         enable_logging=True
        ...     ) as client:
        ...         server_info = await client.get_server_info()
        ...         print(f"Server: {server_info.name}")
        ...
        ...     # Or use as context manager factory
        ...     async with AsyncOutlineClient.create(
        ...         "https://example.com:1234/secret",
        ...         "ab12cd34..."
        ...     ) as client:
        ...         await client.get_server_info()

    """

    def __init__(
            self,
            api_url: str,
            cert_sha256: str,
            *,
            json_format: bool = False,
            timeout: int = 30,
            retry_attempts: int = 3,
            enable_logging: bool = False,
            user_agent: Optional[str] = None,
            max_connections: int = 10,
            rate_limit_delay: float = 0.0,
    ) -> None:

        # Validate api_url
        if not api_url or not api_url.strip():
            raise ValueError("api_url cannot be empty or whitespace")

        # Validate cert_sha256
        if not cert_sha256 or not cert_sha256.strip():
            raise ValueError("cert_sha256 cannot be empty or whitespace")

        # Additional validation for cert_sha256 format (should be hex)
        cert_sha256_clean = cert_sha256.strip()
        if not all(c in '0123456789abcdefABCDEF' for c in cert_sha256_clean):
            raise ValueError("cert_sha256 must contain only hexadecimal characters")

        # Check cert_sha256 length (SHA-256 should be 64 hex characters)
        if len(cert_sha256_clean) != 64:
            raise ValueError("cert_sha256 must be exactly 64 hexadecimal characters (SHA-256)")

        self._api_url = api_url.rstrip("/")
        self._cert_sha256 = cert_sha256
        self._json_format = json_format
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._ssl_context: Optional[Fingerprint] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._retry_attempts = retry_attempts
        self._enable_logging = enable_logging
        self._user_agent = user_agent or f"PyOutlineAPI/0.3.0"
        self._max_connections = max_connections
        self._rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

        # Health check state
        self._last_health_check: float = 0.0
        self._health_check_interval: float = 300.0  # 5 minutes
        self._is_healthy: bool = True

        if enable_logging:
            self._setup_logging()

    @staticmethod
    def _setup_logging() -> None:
        """Setup logging configuration if not already configured."""
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

    @classmethod
    @asynccontextmanager
    async def create(
            cls,
            api_url: str,
            cert_sha256: str,
            **kwargs
    ) -> AsyncGenerator[AsyncOutlineClient, None]:
        """
        Factory method that returns an async context manager.

        This is the recommended way to create clients for one-off operations.
        """
        client = cls(api_url, cert_sha256, **kwargs)
        async with client:
            yield client

    async def __aenter__(self) -> AsyncOutlineClient:
        """Set up client session."""
        headers = {"User-Agent": self._user_agent}

        connector = aiohttp.TCPConnector(
            ssl=self._get_ssl_context(),
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
            logger.info(f"Initialized OutlineAPI client for {self._api_url}")

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up client session."""
        if self._session:
            await self._session.close()
            self._session = None

            if self._enable_logging:
                logger.info("OutlineAPI client session closed")

    async def _apply_rate_limiting(self) -> None:
        """Apply rate limiting if configured."""
        if self._rate_limit_delay <= 0:
            return

        time_since_last = time.time() - self._last_request_time
        if time_since_last < self._rate_limit_delay:
            delay = self._rate_limit_delay - time_since_last
            await asyncio.sleep(delay)

        self._last_request_time = time.time()

    async def health_check(self, force: bool = False) -> bool:
        """
        Perform a health check on the Outline server.

        Args:
            force: Force health check even if recently performed

        Returns:
            True if server is healthy
        """
        current_time = time.time()

        if not force and (current_time - self._last_health_check) < self._health_check_interval:
            return self._is_healthy

        try:
            await self.get_server_info()
            self._is_healthy = True
            if self._enable_logging:
                logger.info("Health check passed")

            return self._is_healthy
        except Exception as e:
            self._is_healthy = False
            if self._enable_logging:
                logger.warning(f"Health check failed: {e}")

            return self._is_healthy
        finally:
            self._last_health_check = current_time

    @overload
    async def _parse_response(
            self,
            response: ClientResponse,
            model: type[BaseModel],
            json_format: Literal[True],
    ) -> JsonDict:
        ...

    @overload
    async def _parse_response(
            self,
            response: ClientResponse,
            model: type[BaseModel],
            json_format: Literal[False],
    ) -> BaseModel:
        ...

    @overload
    async def _parse_response(
            self, response: ClientResponse, model: type[BaseModel], json_format: bool
    ) -> ResponseType:
        ...

    @ensure_context
    async def _parse_response(
            self,
            response: ClientResponse,
            model: type[BaseModel],
            json_format: bool = False,
    ) -> ResponseType:
        """
        Parse and validate API response data.

        Args:
            response: API response to parse
            model: Pydantic model for validation
            json_format: Whether to return raw JSON

        Returns:
            Validated response data

        Raises:
            ValueError: If response validation fails
        """
        try:
            data = await response.json()
            validated = model.model_validate(data)
            return validated.model_dump(by_alias=True) if json_format else validated
        except aiohttp.ContentTypeError as content_error:
            raise ValueError("Invalid response format") from content_error
        except Exception as exception:
            raise ValueError(f"Validation error: {exception}") from exception

    @staticmethod
    async def _handle_error_response(response: ClientResponse) -> None:
        """Handle error responses from the API."""
        try:
            error_data = await response.json()
            error = ErrorResponse.model_validate(error_data)
            raise APIError(f"{error.code}: {error.message}", response.status)
        except (ValueError, aiohttp.ContentTypeError):
            raise APIError(
                f"HTTP {response.status}: {response.reason}", response.status
            )

    @ensure_context
    async def _request(
            self,
            method: str,
            endpoint: str,
            *,
            json: Any = None,
            params: Optional[JsonDict] = None,
    ) -> Any:
        """Make an API request."""
        await self._apply_rate_limiting()
        url = self._build_url(endpoint)
        return await self._make_request(method, url, json, params)

    async def _make_request(
            self,
            method: str,
            url: str,
            json: Any = None,
            params: Optional[JsonDict] = None,
    ) -> Any:
        """Internal method to execute the actual request with retry logic."""

        async def _do_request() -> Any:
            if self._enable_logging:
                # Don't log sensitive data
                safe_url = url.split('?')[0] if '?' in url else url
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
                    await self._handle_error_response(response)

                if response.status == 204:
                    return True

                try:
                    # See #b1746e6
                    await response.json()
                    return response
                except Exception as exception:
                    raise APIError(
                        f"Failed to process response: {exception}", response.status
                    )

        return await self._retry_request(_do_request, attempts=self._retry_attempts)

    @staticmethod
    async def _retry_request(
            request_func: Callable[[], Awaitable[T]],
            *,
            attempts: int = DEFAULT_RETRY_ATTEMPTS,
            delay: float = DEFAULT_RETRY_DELAY,
    ) -> T:
        """
        Execute request with retry logic.

        Args:
            request_func: Async function to execute
            attempts: Maximum number of retry attempts
            delay: Delay between retries in seconds

        Returns:
            Response from the successful request

        Raises:
            APIError: If all retry attempts fail
        """
        last_error = None

        for attempt in range(attempts):
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
                if attempt < attempts - 1:
                    await asyncio.sleep(delay * (attempt + 1))

        raise APIError(
            f"Request failed after {attempts} attempts: {last_error}",
            getattr(last_error, "status_code", None),
        )

    def _build_url(self, endpoint: str) -> str:
        """Build and validate the full URL for the API request."""
        if not isinstance(endpoint, str):
            raise ValueError("Endpoint must be a string")

        url = f"{self._api_url}/{endpoint.lstrip('/')}"
        parsed_url = urlparse(url)

        if not all([parsed_url.scheme, parsed_url.netloc]):
            raise ValueError(f"Invalid URL: {url}")

        return url

    def _get_ssl_context(self) -> Optional[Fingerprint]:
        """Create an SSL context if a certificate fingerprint is provided."""
        if not self._cert_sha256:
            return None

        try:
            return Fingerprint(binascii.unhexlify(self._cert_sha256))
        except binascii.Error as validation_error:
            raise ValueError(
                f"Invalid certificate SHA256: {self._cert_sha256}"
            ) from validation_error
        except Exception as exception:
            raise OutlineError("Failed to create SSL context") from exception

    # Server Management Methods

    @log_method_call
    async def get_server_info(self) -> Union[JsonDict, Server]:
        """
        Get server information.

        Returns:
            Server information including name, ID, and configuration.

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         server = await client.get_server_info()
            ...         print(f"Server {server.name} running version {server.version}")
        """
        response = await self._request("GET", "server")
        return await self._parse_response(
            response, Server, json_format=self._json_format
        )

    @log_method_call
    async def rename_server(self, name: str) -> bool:
        """
        Rename the server.

        Args:
            name: New server name

        Returns:
            True if successful

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         success = await client.rename_server("My VPN Server")
            ...         if success:
            ...             print("Server renamed successfully")
        """
        request = ServerNameRequest(name=name)
        return await self._request(
            "PUT", "name", json=request.model_dump(by_alias=True)
        )

    @log_method_call
    async def set_hostname(self, hostname: str) -> bool:
        """
        Set server hostname for access keys.

        Args:
            hostname: New hostname or IP address

        Returns:
            True if successful

        Raises:
            APIError: If hostname is invalid

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         await client.set_hostname("vpn.example.com")
            ...         # Or use IP address
            ...         await client.set_hostname("203.0.113.1")
        """
        request = HostnameRequest(hostname=hostname)
        return await self._request(
            "PUT",
            "server/hostname-for-access-keys",
            json=request.model_dump(by_alias=True),
        )

    @log_method_call
    async def set_default_port(self, port: int) -> bool:
        """
        Set default port for new access keys.

        Args:
            port: Port number (1025-65535)

        Returns:
            True if successful

        Raises:
            APIError: If port is invalid or in use

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         await client.set_default_port(8388)
        """
        if port < MIN_PORT or port > MAX_PORT:
            raise ValueError(
                f"Privileged ports are not allowed. Use range: {MIN_PORT}-{MAX_PORT}"
            )

        request = PortRequest(port=port)
        return await self._request(
            "PUT",
            "server/port-for-new-access-keys",
            json=request.model_dump(by_alias=True),
        )

    # Metrics Methods

    @log_method_call
    async def get_metrics_status(self) -> Union[JsonDict, MetricsStatusResponse]:
        """
        Get whether metrics collection is enabled.

        Returns:
            Current metrics collection status

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         status = await client.get_metrics_status()
            ...         if status.metrics_enabled:
            ...             print("Metrics collection is enabled")
        """
        response = await self._request("GET", "metrics/enabled")
        return await self._parse_response(
            response, MetricsStatusResponse, json_format=self._json_format
        )

    @log_method_call
    async def set_metrics_status(self, enabled: bool) -> bool:
        """
        Enable or disable metrics collection.

        Args:
            enabled: Whether to enable metrics

        Returns:
            True if successful

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Enable metrics
            ...         await client.set_metrics_status(True)
            ...         # Check new status
            ...         status = await client.get_metrics_status()
        """
        request = MetricsEnabledRequest(metricsEnabled=enabled)
        return await self._request(
            "PUT", "metrics/enabled", json=request.model_dump(by_alias=True)
        )

    @log_method_call
    async def get_transfer_metrics(self) -> Union[JsonDict, ServerMetrics]:
        """
        Get transfer metrics for all access keys.

        Returns:
            Transfer metrics data for each access key

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         metrics = await client.get_transfer_metrics()
            ...         for user_id, bytes_transferred in metrics.bytes_transferred_by_user_id.items():
            ...             print(f"User {user_id}: {bytes_transferred / 1024**3:.2f} GB")
        """
        response = await self._request("GET", "metrics/transfer")
        return await self._parse_response(
            response, ServerMetrics, json_format=self._json_format
        )

    @log_method_call
    async def get_experimental_metrics(
            self, since: str
    ) -> Union[JsonDict, ExperimentalMetrics]:
        """
        Get experimental server metrics.

        Args:
            since: Required time range filter (e.g., "24h", "7d", "30d", or ISO timestamp)

        Returns:
            Detailed server and access key metrics

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Get metrics for the last 24 hours
            ...         metrics = await client.get_experimental_metrics("24h")
            ...         print(f"Server tunnel time: {metrics.server.tunnel_time.seconds}s")
            ...         print(f"Server data transferred: {metrics.server.data_transferred.bytes} bytes")
            ...
            ...         # Get metrics for the last 7 days
            ...         metrics = await client.get_experimental_metrics("7d")
            ...
            ...         # Get metrics since specific timestamp
            ...         metrics = await client.get_experimental_metrics("2024-01-01T00:00:00Z")
        """
        if not since or not since.strip():
            raise ValueError("Parameter 'since' is required and cannot be empty")

        params = {"since": since}
        response = await self._request(
            "GET", "experimental/server/metrics", params=params
        )
        return await self._parse_response(
            response, ExperimentalMetrics, json_format=self._json_format
        )

    # Access Key Management Methods

    @log_method_call
    async def create_access_key(
            self,
            *,
            name: Optional[str] = None,
            password: Optional[str] = None,
            port: Optional[int] = None,
            method: Optional[str] = None,
            limit: Optional[DataLimit] = None,
    ) -> Union[JsonDict, AccessKey]:
        """
        Create a new access key.

        Args:
            name: Optional key name
            password: Optional password
            port: Optional port number (1-65535)
            method: Optional encryption method
            limit: Optional data transfer limit

        Returns:
            New access key details

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Create basic key
            ...         key = await client.create_access_key(name="User 1")
            ...
            ...         # Create key with data limit
            ...         lim = DataLimit(bytes=5 * 1024**3)  # 5 GB
            ...         key = await client.create_access_key(
            ...             name="Limited User",
            ...             port=8388,
            ...             limit=lim
            ...         )
            ...         print(f"Created key: {key.access_url}")
        """
        request = AccessKeyCreateRequest(
            name=name, password=password, port=port, method=method, limit=limit
        )
        response = await self._request(
            "POST",
            "access-keys",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        return await self._parse_response(
            response, AccessKey, json_format=self._json_format
        )

    @log_method_call
    async def create_access_key_with_id(
            self,
            key_id: str,
            *,
            name: Optional[str] = None,
            password: Optional[str] = None,
            port: Optional[int] = None,
            method: Optional[str] = None,
            limit: Optional[DataLimit] = None,
    ) -> Union[JsonDict, AccessKey]:
        """
        Create a new access key with specific ID.

        Args:
            key_id: Specific ID for the access key
            name: Optional key name
            password: Optional password
            port: Optional port number (1-65535)
            method: Optional encryption method
            limit: Optional data transfer limit

        Returns:
            New access key details

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         key = await client.create_access_key_with_id(
            ...             "my-custom-id",
            ...             name="Custom Key"
            ...         )
        """
        request = AccessKeyCreateRequest(
            name=name, password=password, port=port, method=method, limit=limit
        )
        response = await self._request(
            "PUT",
            f"access-keys/{key_id}",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        return await self._parse_response(
            response, AccessKey, json_format=self._json_format
        )

    @log_method_call
    async def get_access_keys(self) -> Union[JsonDict, AccessKeyList]:
        """
        Get all access keys.

        Returns:
            List of all access keys

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         keys = await client.get_access_keys()
            ...         for key in keys.access_keys:
            ...             print(f"Key {key.id}: {key.name or 'unnamed'}")
            ...             if key.data_limit:
            ...                 print(f"  Limit: {key.data_limit.bytes / 1024**3:.1f} GB")
        """
        response = await self._request("GET", "access-keys")
        return await self._parse_response(
            response, AccessKeyList, json_format=self._json_format
        )

    @log_method_call
    async def get_access_key(self, key_id: str) -> Union[JsonDict, AccessKey]:
        """
        Get specific access key.

        Args:
            key_id: Access key ID

        Returns:
            Access key details

        Raises:
            APIError: If key doesn't exist

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         key = await client.get_access_key("1")
            ...         print(f"Port: {key.port}")
            ...         print(f"URL: {key.access_url}")
        """
        response = await self._request("GET", f"access-keys/{key_id}")
        return await self._parse_response(
            response, AccessKey, json_format=self._json_format
        )

    @log_method_call
    async def rename_access_key(self, key_id: str, name: str) -> bool:
        """
        Rename access key.

        Args:
            key_id: Access key ID
            name: New name

        Returns:
            True if successful

        Raises:
            APIError: If key doesn't exist

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Rename key
            ...         await client.rename_access_key("1", "Alice")
            ...
            ...         # Verify new name
            ...         key = await client.get_access_key("1")
            ...         assert key.name == "Alice"
        """
        request = AccessKeyNameRequest(name=name)
        return await self._request(
            "PUT", f"access-keys/{key_id}/name", json=request.model_dump(by_alias=True)
        )

    @log_method_call
    async def delete_access_key(self, key_id: str) -> bool:
        """
        Delete access key.

        Args:
            key_id: Access key ID

        Returns:
            True if successful

        Raises:
            APIError: If key doesn't exist

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         if await client.delete_access_key("1"):
            ...             print("Key deleted")
        """
        return await self._request("DELETE", f"access-keys/{key_id}")

    @log_method_call
    async def set_access_key_data_limit(self, key_id: str, bytes_limit: int) -> bool:
        """
        Set data transfer limit for access key.

        Args:
            key_id: Access key ID
            bytes_limit: Limit in bytes (must be non-negative)

        Returns:
            True if successful

        Raises:
            APIError: If key doesn't exist or limit is invalid

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Set 5 GB limit
            ...         limit = 5 * 1024**3  # 5 GB in bytes
            ...         await client.set_access_key_data_limit("1", limit)
            ...
            ...         # Verify limit
            ...         key = await client.get_access_key("1")
            ...         assert key.data_limit and key.data_limit.bytes == limit
        """
        request = DataLimitRequest(limit=DataLimit(bytes=bytes_limit))
        return await self._request(
            "PUT",
            f"access-keys/{key_id}/data-limit",
            json=request.model_dump(by_alias=True),
        )

    @log_method_call
    async def remove_access_key_data_limit(self, key_id: str) -> bool:
        """
        Remove data transfer limit from access key.

        Args:
            key_id: Access key ID

        Returns:
            True if successful

        Raises:
            APIError: If key doesn't exist

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         await client.remove_access_key_data_limit("1")
        """
        return await self._request("DELETE", f"access-keys/{key_id}/data-limit")

    # Global Data Limit Methods

    @log_method_call
    async def set_global_data_limit(self, bytes_limit: int) -> bool:
        """
        Set global data transfer limit for all access keys.

        Args:
            bytes_limit: Limit in bytes (must be non-negative)

        Returns:
            True if successful

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Set 100 GB global limit
            ...         await client.set_global_data_limit(100 * 1024**3)
        """
        request = DataLimitRequest(limit=DataLimit(bytes=bytes_limit))
        return await self._request(
            "PUT",
            "server/access-key-data-limit",
            json=request.model_dump(by_alias=True),
        )

    @log_method_call
    async def remove_global_data_limit(self) -> bool:
        """
        Remove global data transfer limit.

        Returns:
            True if successful

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         await client.remove_global_data_limit()
        """
        return await self._request("DELETE", "server/access-key-data-limit")

    # Batch Operations

    async def batch_create_access_keys(
            self,
            keys_config: list[dict[str, Any]],
            fail_fast: bool = True
    ) -> list[Union[AccessKey, Exception]]:
        """
        Create multiple access keys in batch.

        Args:
            keys_config: List of key configurations (same as create_access_key kwargs)
            fail_fast: If True, stop on first error. If False, continue and return errors.

        Returns:
            List of created keys or exceptions

        Examples:
            >>> async def main():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         configs = [
            ...             {"name": "User1", "limit": DataLimit(bytes=1024**3)},
            ...             {"name": "User2", "port": 8388},
            ...         ]
            ...         res = await client.batch_create_access_keys(configs)
        """
        results = []

        for config in keys_config:
            try:
                key = await self.create_access_key(**config)
                results.append(key)
            except Exception as e:
                if fail_fast:
                    raise
                results.append(e)

        return results

    async def get_server_summary(self, metrics_since: str = "24h") -> dict[str, Any]:
        """
        Get comprehensive server summary including info, metrics, and key count.

        Args:
            metrics_since: Time range for experimental metrics (default: "24h")

        Returns:
            Dictionary with server info, health status, and statistics
        """
        summary = {}

        try:
            # Get basic server info
            server_info = await self.get_server_info()
            summary["server"] = server_info.model_dump() if isinstance(server_info, BaseModel) else server_info

            # Get access keys count
            keys = await self.get_access_keys()
            key_list = keys.access_keys if isinstance(keys, BaseModel) else keys.get("accessKeys", [])
            summary["access_keys_count"] = len(key_list)

            # Get metrics if available
            try:
                metrics_status = await self.get_metrics_status()
                if (isinstance(metrics_status, BaseModel) and metrics_status.metrics_enabled) or \
                        (isinstance(metrics_status, dict) and metrics_status.get("metricsEnabled")):
                    transfer_metrics = await self.get_transfer_metrics()
                    summary["transfer_metrics"] = transfer_metrics.model_dump() if isinstance(transfer_metrics,
                                                                                              BaseModel) else transfer_metrics

                    # Try to get experimental metrics
                    try:
                        experimental_metrics = await self.get_experimental_metrics(metrics_since)
                        summary["experimental_metrics"] = experimental_metrics.model_dump() if isinstance(
                            experimental_metrics,
                            BaseModel) else experimental_metrics
                    except Exception:
                        summary["experimental_metrics"] = None
            except Exception:
                summary["transfer_metrics"] = None
                summary["experimental_metrics"] = None

            summary["healthy"] = True

        except Exception as e:
            summary["healthy"] = False
            summary["error"] = str(e)

        return summary

    # Utility and management methods

    def configure_logging(self, level: str = "INFO", format_string: Optional[str] = None) -> None:
        """
        Configure logging for the client.

        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
            format_string: Custom format string for log messages
        """
        self._enable_logging = True

        # Clear existing handlers
        logger.handlers.clear()

        handler = logging.StreamHandler()
        if format_string:
            formatter = logging.Formatter(format_string)
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level.upper()))

    @property
    def is_healthy(self) -> bool:
        """Check if the last health check passed."""
        return self._is_healthy

    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        """Access the current client session."""
        return self._session

    @property
    def api_url(self) -> str:
        """Get the API URL (without sensitive parts)."""
        from urllib.parse import urlparse
        parsed = urlparse(self._api_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def __repr__(self) -> str:
        """String representation of the client."""
        status = "connected" if self._session and not self._session.closed else "disconnected"
        return f"AsyncOutlineClient(url={self.api_url}, status={status})"
