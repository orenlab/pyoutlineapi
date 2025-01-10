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

import binascii
from functools import wraps
from typing import (
    Any,
    Literal,
    TypeAlias,
    Union,
    overload,
    Optional,
    ParamSpec,
    TypeVar,
    Callable,
)
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientResponse, Fingerprint
from pydantic import BaseModel

from .models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    DataLimit,
    ErrorResponse,
    MetricsPeriod,
    MetricsStatusResponse,
    Server,
    ServerMetrics,
)

# Type variables for decorator
P = ParamSpec("P")
T = TypeVar("T")

# Type aliases
JsonDict: TypeAlias = dict[str, Any]
ResponseType = Union[JsonDict, BaseModel]


class OutlineError(Exception):
    """Base exception for Outline client errors."""


class APIError(OutlineError):
    """Raised when API requests fail."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def ensure_context(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to ensure client session is initialized."""

    @wraps(func)
    async def wrapper(self: AsyncOutlineClient, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self._session or self._session.closed:
            raise RuntimeError("Client session is not initialized or already closed.")
        return await func(self, *args, **kwargs)

    return wrapper


class AsyncOutlineClient:
    """
    Asynchronous client for the Outline VPN Server API.

    Args:
        api_url: Base URL for the Outline server API
        cert_sha256: SHA-256 fingerprint of the server's TLS certificate
        json_format: Return raw JSON instead of Pydantic models
        timeout: Request timeout in seconds

    Examples:
        >>> async def doo_something():
        ...     async with AsyncOutlineClient(
        ...         "https://example.com:1234/secret",
        ...         "ab12cd34..."
        ...     ) as client:
        ...         server_info = await client.get_server_info()
    """

    def __init__(
        self,
        api_url: str,
        cert_sha256: str,
        *,
        json_format: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._cert_sha256 = cert_sha256
        self._json_format = json_format
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._ssl_context: Optional[Fingerprint] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> AsyncOutlineClient:
        """Set up client session for context manager."""
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            raise_for_status=False,
            connector=aiohttp.TCPConnector(ssl=self._get_ssl_context()),
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up client session."""
        if self._session:
            await self._session.close()
            self._session = None

    @overload
    async def _parse_response(
        self,
        response: ClientResponse,
        model: type[BaseModel],
        json_format: Literal[True],
    ) -> JsonDict: ...

    @overload
    async def _parse_response(
        self,
        response: ClientResponse,
        model: type[BaseModel],
        json_format: Literal[False],
    ) -> BaseModel: ...

    @overload
    async def _parse_response(
        self, response: ClientResponse, model: type[BaseModel], json_format: bool
    ) -> Union[JsonDict, BaseModel]: ...

    @ensure_context
    async def _parse_response(
        self, response: ClientResponse, model: type[BaseModel], json_format: bool = True
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
            return validated.model_dump() if json_format else validated
        except aiohttp.ContentTypeError as e:
            raise ValueError("Invalid response format") from e
        except Exception as e:
            raise ValueError(f"Validation error: {e}") from e

    @staticmethod
    async def _handle_error_response(response: ClientResponse) -> None:
        """Handle error responses from the API."""
        try:
            error_data = await response.json()
            error = ErrorResponse.model_validate(error_data)
            raise APIError(f"{error.code}: {error.message}", response.status)
        except ValueError:
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
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Make an API request."""
        url = self._build_url(endpoint)

        async with self._session.request(
            method,
            url,
            json=json,
            params=params,
            raise_for_status=False,
        ) as response:
            if response.status >= 400:
                await self._handle_error_response(response)

            if response.status == 204:
                return True

            try:
                await response.json()
                return response
            except aiohttp.ContentTypeError:
                return await response.text()
            except Exception as e:
                raise APIError(f"Failed to parse response: {e}", response.status)

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
        except binascii.Error as e:
            raise ValueError(f"Invalid certificate SHA256: {self._cert_sha256}") from e
        except Exception as e:
            raise OutlineError("Failed to create SSL context") from e

    async def get_server_info(self) -> Union[JsonDict, Server]:
        """
        Get server information.

        Returns:
            Server information including name, ID, and configuration.

        Examples:
            >>> async def doo_something():
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

    async def rename_server(self, name: str) -> bool:
        """
        Rename the server.

        Args:
            name: New server name

        Returns:
            True if successful

        Examples:
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...     success = await client.rename_server("My VPN Server")
            ...     if success:
            ...         print("Server renamed successfully")
        """
        return await self._request("PUT", "name", json={"name": name})

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
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         await client.set_hostname("vpn.example.com")
            ...         # Or use IP address
            ...         await client.set_hostname("203.0.113.1")
        """
        return await self._request(
            "PUT", "server/hostname-for-access-keys", json={"hostname": hostname}
        )

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
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         await client.set_default_port(8388)

        """
        if port < 1025 or port > 65535:
            raise ValueError("Privileged ports are not allowed. Use range: 1025-65535")

        return await self._request(
            "PUT", "server/port-for-new-access-keys", json={"port": port}
        )

    async def get_metrics_status(self) -> dict[str, Any] | BaseModel:
        """
        Get whether metrics collection is enabled.

        Returns:
            Current metrics collection status

        Examples:
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         if await client.get_metrics_status():
            ...             print("Metrics collection is enabled")
        """
        response = await self._request("GET", "metrics/enabled")
        data = await self._parse_response(
            response, MetricsStatusResponse, json_format=self._json_format
        )
        return data

    async def set_metrics_status(self, enabled: bool) -> bool:
        """
        Enable or disable metrics collection.

        Args:
            enabled: Whether to enable metrics

        Returns:
            True if successful

        Examples:
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Enable metrics
            ...         await client.set_metrics_status(True)
            ...         # Check new status
            ...         is_enabled = await client.get_metrics_status()
        """
        return await self._request(
            "PUT", "metrics/enabled", json={"metricsEnabled": enabled}
        )

    async def get_transfer_metrics(
        self, period: MetricsPeriod = MetricsPeriod.MONTHLY
    ) -> Union[JsonDict, ServerMetrics]:
        """
        Get transfer metrics for specified period.

        Args:
            period: Time period for metrics (DAILY, WEEKLY, or MONTHLY)

        Returns:
            Transfer metrics data for each access key

        Examples:
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Get monthly metrics
            ...         metrics = await client.get_transfer_metrics()
            ...         # Or get daily metrics
            ...         daily = await client.get_transfer_metrics(MetricsPeriod.DAILY)
            ...         for user_id, bytes_transferred in daily.bytes_transferred_by_user_id.items():
            ...             print(f"User {user_id}: {bytes_transferred / 1024**3:.2f} GB")
        """
        response = await self._request(
            "GET", "metrics/transfer", params={"period": period.value}
        )
        return await self._parse_response(
            response, ServerMetrics, json_format=self._json_format
        )

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
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Create basic key
            ...         key = await client.create_access_key(name="User 1")
            ...
            ...         # Create key with data limit
            ...         _limit = DataLimit(bytes=5 * 1024**3)  # 5 GB
            ...         key = await client.create_access_key(
            ...             name="Limited User",
            ...             port=8388,
            ...             limit=_limit
            ...         )
            ...         print(f"Created key: {key.access_url}")
        """
        request = AccessKeyCreateRequest(
            name=name, password=password, port=port, method=method, limit=limit
        )
        response = await self._request(
            "POST", "access-keys", json=request.model_dump(exclude_none=True)
        )
        return await self._parse_response(
            response, AccessKey, json_format=self._json_format
        )

    async def get_access_keys(self) -> Union[JsonDict, AccessKeyList]:
        """
        Get all access keys.

        Returns:
            List of all access keys

        Examples:
            >>> async def doo_something():
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

    async def get_access_key(self, key_id: int) -> Union[JsonDict, AccessKey]:
        """
        Get specific access key.

        Args:
            key_id: Access key ID

        Returns:
            Access key details

        Raises:
            APIError: If key doesn't exist

        Examples:
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         key = await client.get_access_key(1)
            ...         print(f"Port: {key.port}")
            ...         print(f"URL: {key.access_url}")
        """
        response = await self._request("GET", f"access-keys/{key_id}")
        return await self._parse_response(
            response, AccessKey, json_format=self._json_format
        )

    async def rename_access_key(self, key_id: int, name: str) -> bool:
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
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Rename key
            ...         await client.rename_access_key(1, "Alice")
            ...
            ...         # Verify new name
            ...         key = await client.get_access_key(1)
            ...         assert key.name == "Alice"
        """
        return await self._request(
            "PUT", f"access-keys/{key_id}/name", json={"name": name}
        )

    async def delete_access_key(self, key_id: int) -> bool:
        """
        Delete access key.

        Args:
            key_id: Access key ID

        Returns:
            True if successful

        Raises:
            APIError: If key doesn't exist

        Examples:
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         if await client.delete_access_key(1):
            ...             print("Key deleted")

        """
        return await self._request("DELETE", f"access-keys/{key_id}")

    async def set_access_key_data_limit(self, key_id: int, bytes_limit: int) -> bool:
        """
        Set data transfer limit for access key.

        Args:
            key_id: Access key ID
            bytes_limit: Limit in bytes (must be positive)

        Returns:
            True if successful

        Raises:
            APIError: If key doesn't exist or limit is invalid

        Examples:
            >>> async def doo_something():
            ...     async with AsyncOutlineClient(
            ...         "https://example.com:1234/secret",
            ...         "ab12cd34..."
            ...     ) as client:
            ...         # Set 5 GB limit
            ...         limit = 5 * 1024**3  # 5 GB in bytes
            ...         await client.set_access_key_data_limit(1, limit)
            ...
            ...         # Verify limit
            ...         key = await client.get_access_key(1)
            ...         assert key.data_limit and key.data_limit.bytes == limit
        """
        return await self._request(
            "PUT",
            f"access-keys/{key_id}/data-limit",
            json={"limit": {"bytes": bytes_limit}},
        )

    async def remove_access_key_data_limit(self, key_id: int) -> bool:
        """
        Remove data transfer limit from access key.

        Args:
            key_id: Access key ID

        Returns:
            True if successful

        Raises:
            APIError: If key doesn't exist
        """
        return await self._request("DELETE", f"access-keys/{key_id}/data-limit")

    @property
    def session(self):
        return self._session
