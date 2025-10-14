"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: API endpoint mixins matching official Outline API schema.
Schema: https://github.com/Jigsaw-Code/outline-server/blob/master/src/shadowbox/server/api.yml
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .common_types import Validators
from .models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    AccessKeyNameRequest,
    DataLimit,
    DataLimitRequest,
    ExperimentalMetrics,
    HostnameRequest,
    MetricsEnabledRequest,
    MetricsStatusResponse,
    PortRequest,
    Server,
    ServerMetrics,
    ServerNameRequest,
)
from .response_parser import JsonDict, ResponseParser

logger = logging.getLogger(__name__)


class HTTPClientProtocol(Protocol):
    """Protocol for HTTP client with PRIVATE request method."""

    async def _request(
            self,
            method: str,
            endpoint: str,
            *,
            json: Any = None,
            params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Internal request method.

        Note: This is a private method and should not be called directly.
        Use high-level API methods instead.
        """
        ...

    def _resolve_json_format(self, as_json: bool | None) -> bool:
        """
        Resolve JSON format preference.

        If as_json is None, uses config.json_format as default.
        """
        ...


class ServerMixin:
    """
    Server management operations.

    Provides methods for:
    - Getting server information
    - Renaming server
    - Setting hostname for access keys
    - Configuring default port for new keys

    API Endpoints:
    - GET /server
    - PUT /name
    - PUT /server/hostname-for-access-keys
    - PUT /server/port-for-new-access-keys
    """

    async def get_server_info(
            self: HTTPClientProtocol,
            *,
            as_json: bool | None = None,
    ) -> Server | JsonDict:
        """
        Get server information and configuration.

        API: GET /server

        Args:
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            Server: Server information model
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     server = await client.get_server_info()
            ...     print(f"Name: {server.name}")
            ...     print(f"Port: {server.port_for_new_access_keys}")
        """
        data = await self._request("GET", "server")
        return ResponseParser.parse(
            data, Server, as_json=self._resolve_json_format(as_json)
        )

    async def rename_server(self: HTTPClientProtocol, name: str) -> bool:
        """
        Rename the server.

        API: PUT /name

        Args:
            name: New server name (1-255 characters)

        Returns:
            bool: True if successful

        Raises:
            ValueError: If name is empty or too long

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     success = await client.rename_server("Production VPN")
            ...     print(f"Renamed: {success}")
        """
        validated_name = Validators.validate_name(name)
        if validated_name is None:
            raise ValueError("Server name cannot be empty")

        request = ServerNameRequest(name=validated_name)
        data = await self._request(
            "PUT", "name", json=request.model_dump(by_alias=True)
        )
        return ResponseParser.parse_simple(data)

    async def set_hostname(self: HTTPClientProtocol, hostname: str) -> bool:
        """
        Set hostname for access keys.

        API: PUT /server/hostname-for-access-keys

        Args:
            hostname: Hostname or IP address for access keys

        Returns:
            bool: True if successful

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     await client.set_hostname("vpn.example.com")
        """
        request = HostnameRequest(hostname=hostname)
        data = await self._request(
            "PUT",
            "server/hostname-for-access-keys",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    async def set_default_port(self: HTTPClientProtocol, port: int) -> bool:
        """
        Set default port for new access keys.

        API: PUT /server/port-for-new-access-keys

        Args:
            port: Port number (1025-65535)

        Returns:
            bool: True if successful

        Raises:
            ValueError: If port is out of valid range

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     await client.set_default_port(8388)
        """
        validated_port = Validators.validate_port(port)
        request = PortRequest(port=validated_port)
        data = await self._request(
            "PUT",
            "server/port-for-new-access-keys",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)


class AccessKeyMixin:
    """
    Access key management operations.

    Provides methods for:
    - Creating access keys
    - Getting access keys (all or specific)
    - Deleting access keys
    - Renaming access keys
    - Managing per-key data limits

    API Endpoints:
    - POST /access-keys
    - PUT /access-keys/{id}
    - GET /access-keys
    - GET /access-keys/{id}
    - DELETE /access-keys/{id}
    - PUT /access-keys/{id}/name
    - PUT /access-keys/{id}/data-limit
    - DELETE /access-keys/{id}/data-limit
    """

    async def create_access_key(
            self: HTTPClientProtocol,
            *,
            name: str | None = None,
            password: str | None = None,
            port: int | None = None,
            method: str | None = None,
            limit: DataLimit | None = None,
            as_json: bool | None = None,
    ) -> AccessKey | JsonDict:
        """
        Create new access key with auto-generated ID.

        API: POST /access-keys

        Args:
            name: Optional key name
            password: Optional password (auto-generated if not provided)
            port: Optional port (uses default if not provided)
            method: Optional encryption method
            limit: Optional data limit
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            AccessKey: Created access key model
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     # Simple creation
            ...     key = await client.create_access_key(name="Alice")
            ...     print(f"Key created: {key.access_url}")
            ...
            ...     # With data limit
            ...     key = await client.create_access_key(
            ...         name="Bob",
            ...         limit=DataLimit(bytes=5 * 1024**3)  # 5 GB
            ...     )
        """
        # Validate inputs
        if name is not None:
            name = Validators.validate_name(name)
        if port is not None:
            port = Validators.validate_port(port)

        request = AccessKeyCreateRequest(
            name=name,
            password=password,
            port=port,
            method=method,
            limit=limit,
        )

        data = await self._request(
            "POST",
            "access-keys",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        return ResponseParser.parse(
            data, AccessKey, as_json=self._resolve_json_format(as_json)
        )

    async def create_access_key_with_id(
            self: HTTPClientProtocol,
            key_id: str,
            *,
            name: str | None = None,
            password: str | None = None,
            port: int | None = None,
            method: str | None = None,
            limit: DataLimit | None = None,
            as_json: bool | None = None,
    ) -> AccessKey | JsonDict:
        """
        Create access key with specific ID.

        API: PUT /access-keys/{id}

        Args:
            key_id: Specific key identifier (alphanumeric, dashes, underscores)
            name: Optional key name
            password: Optional password
            port: Optional port
            method: Optional encryption method
            limit: Optional data limit
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            AccessKey: Created access key model
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Raises:
            ValueError: If key_id is invalid

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     key = await client.create_access_key_with_id(
            ...         key_id="custom-user-001",
            ...         name="Custom User",
            ...     )
        """
        # Validate key_id
        validated_key_id = Validators.validate_key_id(key_id)

        # Validate inputs
        if name is not None:
            name = Validators.validate_name(name)
        if port is not None:
            port = Validators.validate_port(port)

        request = AccessKeyCreateRequest(
            name=name,
            password=password,
            port=port,
            method=method,
            limit=limit,
        )

        data = await self._request(
            "PUT",
            f"access-keys/{validated_key_id}",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        return ResponseParser.parse(
            data, AccessKey, as_json=self._resolve_json_format(as_json)
        )

    async def get_access_keys(
            self: HTTPClientProtocol,
            *,
            as_json: bool | None = None,
    ) -> AccessKeyList | JsonDict:
        """
        Get all access keys.

        API: GET /access-keys

        Args:
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            AccessKeyList: List of all access keys
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     keys = await client.get_access_keys()
            ...     print(f"Total keys: {keys.count}")
            ...     for key in keys.access_keys:
            ...         print(f"- {key.name}: {key.id}")
        """
        data = await self._request("GET", "access-keys")
        return ResponseParser.parse(
            data, AccessKeyList, as_json=self._resolve_json_format(as_json)
        )

    async def get_access_key(
            self: HTTPClientProtocol,
            key_id: str,
            *,
            as_json: bool | None = None,
    ) -> AccessKey | JsonDict:
        """
        Get specific access key by ID.

        API: GET /access-keys/{id}

        Args:
            key_id: Access key identifier
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            AccessKey: Access key details
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     key = await client.get_access_key("key123")
            ...     print(f"Key: {key.name}")
            ...     print(f"URL: {key.access_url}")
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request("GET", f"access-keys/{validated_key_id}")
        return ResponseParser.parse(
            data, AccessKey, as_json=self._resolve_json_format(as_json)
        )

    async def delete_access_key(self: HTTPClientProtocol, key_id: str) -> bool:
        """
        Delete access key.

        API: DELETE /access-keys/{id}

        Args:
            key_id: Access key identifier

        Returns:
            bool: True if successful

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     success = await client.delete_access_key("key123")
            ...     if success:
            ...         print("Key deleted successfully")
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request("DELETE", f"access-keys/{validated_key_id}")
        return ResponseParser.parse_simple(data)

    async def rename_access_key(
            self: HTTPClientProtocol,
            key_id: str,
            name: str,
    ) -> bool:
        """
        Rename access key.

        API: PUT /access-keys/{id}/name

        Args:
            key_id: Access key identifier
            name: New name (1-255 characters)

        Returns:
            bool: True if successful

        Raises:
            ValueError: If name is empty or too long

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     await client.rename_access_key("key123", "Alice's Key")
        """
        validated_key_id = Validators.validate_key_id(key_id)

        validated_name = Validators.validate_name(name)
        if validated_name is None:
            raise ValueError("Name cannot be empty")

        request = AccessKeyNameRequest(name=validated_name)
        data = await self._request(
            "PUT",
            f"access-keys/{validated_key_id}/name",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    async def set_access_key_data_limit(
            self: HTTPClientProtocol,
            key_id: str,
            bytes_limit: int,
    ) -> bool:
        """
        Set data limit for specific access key.

        API: PUT /access-keys/{id}/data-limit

        Args:
            key_id: Access key identifier
            bytes_limit: Limit in bytes (non-negative)

        Returns:
            bool: True if successful

        Raises:
            ValueError: If bytes_limit is negative

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     # Set 10 GB limit
            ...     await client.set_access_key_data_limit(
            ...         "key123",
            ...         10 * 1024**3
            ...     )
        """
        validated_key_id = Validators.validate_key_id(key_id)

        validated_bytes = Validators.validate_non_negative(bytes_limit, "bytes_limit")
        request = DataLimitRequest(limit=DataLimit(bytes=validated_bytes))

        data = await self._request(
            "PUT",
            f"access-keys/{validated_key_id}/data-limit",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    async def remove_access_key_data_limit(
            self: HTTPClientProtocol,
            key_id: str,
    ) -> bool:
        """
        Remove data limit from access key.

        API: DELETE /access-keys/{id}/data-limit

        Args:
            key_id: Access key identifier

        Returns:
            bool: True if successful

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     await client.remove_access_key_data_limit("key123")
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request(
            "DELETE", f"access-keys/{validated_key_id}/data-limit"
        )
        return ResponseParser.parse_simple(data)


class DataLimitMixin:
    """
    Global data limit operations.

    Provides methods for managing server-wide data limits that apply
    to all access keys by default.

    API Endpoints:
    - PUT /server/access-key-data-limit
    - DELETE /server/access-key-data-limit
    """

    async def set_global_data_limit(
            self: HTTPClientProtocol,
            bytes_limit: int,
    ) -> bool:
        """
        Set global data limit for all access keys.

        API: PUT /server/access-key-data-limit

        Args:
            bytes_limit: Limit in bytes (non-negative)

        Returns:
            bool: True if successful

        Raises:
            ValueError: If bytes_limit is negative

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     # Set 50 GB global limit
            ...     await client.set_global_data_limit(50 * 1024**3)
        """
        validated_bytes = Validators.validate_non_negative(bytes_limit, "bytes_limit")
        request = DataLimitRequest(limit=DataLimit(bytes=validated_bytes))

        data = await self._request(
            "PUT",
            "server/access-key-data-limit",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    async def remove_global_data_limit(self: HTTPClientProtocol) -> bool:
        """
        Remove global data limit.

        API: DELETE /server/access-key-data-limit

        Returns:
            bool: True if successful

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     await client.remove_global_data_limit()
        """
        data = await self._request("DELETE", "server/access-key-data-limit")
        return ResponseParser.parse_simple(data)


class MetricsMixin:
    """
    Metrics operations.

    Provides methods for:
    - Checking metrics status
    - Enabling/disabling metrics
    - Getting transfer metrics
    - Getting experimental metrics

    API Endpoints:
    - GET /metrics/enabled
    - PUT /metrics/enabled
    - GET /metrics/transfer
    - GET /experimental/server/metrics
    """

    async def get_metrics_status(
            self: HTTPClientProtocol,
            *,
            as_json: bool | None = None,
    ) -> MetricsStatusResponse | JsonDict:
        """
        Get metrics collection status.

        API: GET /metrics/enabled

        Args:
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            MetricsStatusResponse: Metrics status
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     status = await client.get_metrics_status()
            ...     print(f"Metrics enabled: {status.metrics_enabled}")
        """
        data = await self._request("GET", "metrics/enabled")
        return ResponseParser.parse(
            data, MetricsStatusResponse, as_json=self._resolve_json_format(as_json)
        )

    async def set_metrics_status(self: HTTPClientProtocol, enabled: bool) -> bool:
        """
        Enable or disable metrics collection.

        API: PUT /metrics/enabled

        Args:
            enabled: True to enable, False to disable

        Returns:
            bool: True if successful

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     # Enable metrics
            ...     await client.set_metrics_status(True)
            ...
            ...     # Disable metrics
            ...     await client.set_metrics_status(False)
        """
        request = MetricsEnabledRequest(metricsEnabled=enabled)
        data = await self._request(
            "PUT",
            "metrics/enabled",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    async def get_transfer_metrics(
            self: HTTPClientProtocol,
            *,
            as_json: bool | None = None,
    ) -> ServerMetrics | JsonDict:
        """
        Get transfer metrics for all access keys.

        API: GET /metrics/transfer

        Args:
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            ServerMetrics: Transfer metrics by key ID
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     metrics = await client.get_transfer_metrics()
            ...     print(f"Total bytes: {metrics.total_bytes}")
            ...     for key_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
            ...         print(f"Key {key_id}: {bytes_used / 1024**2:.2f} MB")
        """
        data = await self._request("GET", "metrics/transfer")
        return ResponseParser.parse(
            data, ServerMetrics, as_json=self._resolve_json_format(as_json)
        )

    async def get_experimental_metrics(
            self: HTTPClientProtocol,
            since: str,
            *,
            as_json: bool | None = None,
    ) -> ExperimentalMetrics | JsonDict:
        """
        Get experimental server metrics.

        API: GET /experimental/server/metrics?since={since}

        Args:
            since: Time range (e.g., "24h", "7d", "30d")
            as_json: Return as JSON dict instead of model (None = use config default)

        Returns:
            ExperimentalMetrics: Experimental metrics
            JsonDict: Raw JSON response (if as_json=True or OUTLINE_JSON_FORMAT=true)

        Raises:
            ValueError: If since parameter is empty

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     # Last 24 hours
            ...     metrics = await client.get_experimental_metrics("24h")
            ...     print(f"Server data: {metrics.server.data_transferred.bytes}")
            ...
            ...     # Last 7 days
            ...     metrics = await client.get_experimental_metrics("7d")
        """
        if not since or not since.strip():
            raise ValueError("'since' parameter required")

        data = await self._request(
            "GET",
            "experimental/server/metrics",
            params={"since": since.strip()},
        )
        return ResponseParser.parse(
            data, ExperimentalMetrics, as_json=self._resolve_json_format(as_json)
        )


__all__ = [
    "ServerMixin",
    "AccessKeyMixin",
    "DataLimitMixin",
    "MetricsMixin",
]
