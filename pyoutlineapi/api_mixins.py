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
import logging
from typing import Any, Union, Generic, TypeVar, Callable, Awaitable

from .base_client import HTTPClientProtocol
from .common_types import CommonValidators
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
from .response_parser import ResponseParser, JsonDict

logger = logging.getLogger(__name__)

# Type variables for generic operations
T = TypeVar("T")
R = TypeVar("R")


class BaseMixin:
    """Base class for all API mixins with common functionality."""

    def _get_json_format(self: HTTPClientProtocol) -> bool:
        """Get JSON format setting from client."""
        return getattr(self, "_json_format", False)

    async def _parse_response(
        self: HTTPClientProtocol, response_data: dict[str, Any], model_class: type[T]
    ) -> Union[JsonDict, T]:
        """Parse response using the appropriate format with enhanced error handling."""
        try:
            return await ResponseParser.parse_response_data(
                data=response_data,
                model=model_class,
                json_format=self._get_json_format(),
            )
        except ValueError as e:
            # Log the detailed error but provide a user-friendly message
            logger.error(f"Response parsing failed: {e}")

            # Try to provide helpful context
            if "empty" in str(e).lower() and "name" in str(e).lower():
                # Handle common case of empty names from Outline API
                logger.info(
                    "Attempting to parse response with safe fallback for empty names"
                )
                return await ResponseParser.safe_parse_response_data(
                    data=response_data,
                    model=model_class,
                    json_format=self._get_json_format(),
                    fallback_to_json=True,
                )
            raise


class ServerManagementMixin(BaseMixin):
    """Mixin for server management operations with clean separation."""

    async def get_server_info(self: HTTPClientProtocol) -> Union[JsonDict, Server]:
        """
        Get server information.

        Returns:
            Server information with details about configuration and status

        Raises:
            APIError: If server is unreachable or returns an error
        """
        response_data = await self.request("GET", "server")
        return await self._parse_response(response_data, Server)

    async def rename_server(self: HTTPClientProtocol, name: str) -> bool:
        """
        Rename the server.

        Args:
            name: New server name (will be validated)

        Returns:
            True if rename was successful

        Raises:
            ValueError: If name is invalid
            APIError: If request fails
        """
        # Validate name using common validator
        validated_name = CommonValidators.validate_name(name)

        request = ServerNameRequest(name=validated_name)
        response_data = await self.request(
            "PUT", "name", json=request.model_dump(by_alias=True)
        )
        return ResponseParser.parse_simple_response_data(response_data)

    async def set_hostname(self: HTTPClientProtocol, hostname: str) -> bool:
        """
        Set server hostname for access keys.

        Args:
            hostname: New hostname or IP address

        Returns:
            True if hostname was set successfully

        Raises:
            ValueError: If hostname format is invalid
            APIError: If request fails
        """
        request = HostnameRequest(hostname=hostname)
        response_data = await self.request(
            "PUT",
            "server/hostname-for-access-keys",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple_response_data(response_data)

    async def set_default_port(self: HTTPClientProtocol, port: int) -> bool:
        """
        Set default port for new access keys.

        Args:
            port: Port number (1025-65535)

        Returns:
            True if port was set successfully

        Raises:
            ValueError: If port is outside allowed range
            APIError: If request fails
        """
        # Validate port using common validator
        validated_port = CommonValidators.validate_port(port)

        request = PortRequest(port=validated_port)
        response_data = await self.request(
            "PUT",
            "server/port-for-new-access-keys",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple_response_data(response_data)


class MetricsMixin(BaseMixin):
    """Mixin for metrics operations with enhanced error handling."""

    async def get_metrics_status(
        self: HTTPClientProtocol,
    ) -> Union[JsonDict, MetricsStatusResponse]:
        """
        Get whether metrics collection is enabled.

        Returns:
            Current metrics collection status

        Raises:
            APIError: If request fails
        """
        response_data = await self.request("GET", "metrics/enabled")
        return await self._parse_response(response_data, MetricsStatusResponse)

    async def set_metrics_status(self: HTTPClientProtocol, enabled: bool) -> bool:
        """
        Enable or disable metrics collection.

        Args:
            enabled: Whether to enable metrics collection

        Returns:
            True if metrics status was updated successfully

        Raises:
            APIError: If request fails
        """
        request = MetricsEnabledRequest(metricsEnabled=enabled)
        response_data = await self.request(
            "PUT", "metrics/enabled", json=request.model_dump(by_alias=True)
        )
        return ResponseParser.parse_simple_response_data(response_data)

    async def get_transfer_metrics(
        self: HTTPClientProtocol,
    ) -> Union[JsonDict, ServerMetrics]:
        """
        Get transfer metrics for all access keys.

        Returns:
            Transfer metrics showing data usage per access key

        Raises:
            APIError: If metrics are disabled or request fails
        """
        response_data = await self.request("GET", "metrics/transfer")
        return await self._parse_response(response_data, ServerMetrics)

    async def get_experimental_metrics(
        self: HTTPClientProtocol, since: str
    ) -> Union[JsonDict, ExperimentalMetrics]:
        """
        Get experimental server metrics.

        Args:
            since: Time range for metrics (e.g., "24h", "7d", "30d")

        Returns:
            Detailed experimental metrics including bandwidth and location data

        Raises:
            ValueError: If 'since' parameter is empty
            APIError: If request fails
        """
        if not since or not since.strip():
            raise ValueError("Parameter 'since' is required and cannot be empty")

        params = {"since": since.strip()}
        response_data = await self.request(
            "GET", "experimental/server/metrics", params=params
        )
        return await self._parse_response(response_data, ExperimentalMetrics)


class AccessKeyMixin(BaseMixin):
    """Mixin for access key operations with comprehensive validation."""

    async def create_access_key(
        self: HTTPClientProtocol,
        *,
        name: str | None = None,
        password: str | None = None,
        port: int | None = None,
        method: str | None = None,
        limit: DataLimit | None = None,
    ) -> Union[JsonDict, AccessKey]:
        """
        Create a new access key.

        Args:
            name: Optional access key name
            password: Optional custom password
            port: Optional custom port (1025-65535)
            method: Optional encryption method
            limit: Optional data transfer limit

        Returns:
            Created access key with connection details

        Raises:
            ValueError: If any parameter is invalid
            APIError: If creation fails
        """
        # Validate inputs
        if name is not None:
            name = CommonValidators.validate_name(name)
        if port is not None:
            port = CommonValidators.validate_port(port)

        request = AccessKeyCreateRequest(
            name=name, password=password, port=port, method=method, limit=limit
        )
        response_data = await self.request(
            "POST",
            "access-keys",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        return await self._parse_response(response_data, AccessKey)

    async def create_access_key_with_id(
        self: HTTPClientProtocol,
        key_id: str,
        *,
        name: str | None = None,
        password: str | None = None,
        port: int | None = None,
        method: str | None = None,
        limit: DataLimit | None = None,
    ) -> Union[JsonDict, AccessKey]:
        """
        Create a new access key with specific ID.

        Args:
            key_id: Specific ID for the access key
            name: Optional access key name
            password: Optional custom password
            port: Optional custom port (1025-65535)
            method: Optional encryption method
            limit: Optional data transfer limit

        Returns:
            Created access key with specified ID

        Raises:
            ValueError: If any parameter is invalid
            APIError: If creation fails or ID already exists
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        # Validate inputs
        if name is not None:
            name = CommonValidators.validate_name(name)
        if port is not None:
            port = CommonValidators.validate_port(port)

        request = AccessKeyCreateRequest(
            name=name, password=password, port=port, method=method, limit=limit
        )
        response_data = await self.request(
            "PUT",
            f"access-keys/{key_id.strip()}",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        return await self._parse_response(response_data, AccessKey)

    async def get_access_keys(
        self: HTTPClientProtocol,
    ) -> Union[JsonDict, AccessKeyList]:
        """
        Get all access keys.

        Returns:
            List of all access keys with their details

        Raises:
            APIError: If request fails
        """
        response_data = await self.request("GET", "access-keys")
        return await self._parse_response(response_data, AccessKeyList)

    async def get_access_key(
        self: HTTPClientProtocol, key_id: str
    ) -> Union[JsonDict, AccessKey]:
        """
        Get specific access key.

        Args:
            key_id: Access key identifier

        Returns:
            Access key details

        Raises:
            ValueError: If key_id is empty
            APIError: If key not found or request fails
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        response_data = await self.request("GET", f"access-keys/{key_id.strip()}")
        return await self._parse_response(response_data, AccessKey)

    async def rename_access_key(
        self: HTTPClientProtocol, key_id: str, name: str
    ) -> bool:
        """
        Rename access key.

        Args:
            key_id: Access key identifier
            name: New name for the access key

        Returns:
            True if rename was successful

        Raises:
            ValueError: If key_id is empty or name is invalid
            APIError: If key not found or request fails
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        validated_name = CommonValidators.validate_name(name)

        request = AccessKeyNameRequest(name=validated_name)
        response_data = await self.request(
            "PUT",
            f"access-keys/{key_id.strip()}/name",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple_response_data(response_data)

    async def delete_access_key(self: HTTPClientProtocol, key_id: str) -> bool:
        """
        Delete access key.

        Args:
            key_id: Access key identifier

        Returns:
            True if deletion was successful

        Raises:
            ValueError: If key_id is empty
            APIError: If key not found or request fails
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        response_data = await self.request("DELETE", f"access-keys/{key_id.strip()}")
        return ResponseParser.parse_simple_response_data(response_data)

    async def set_access_key_data_limit(
        self: HTTPClientProtocol, key_id: str, bytes_limit: int
    ) -> bool:
        """
        Set data transfer limit for access key.

        Args:
            key_id: Access key identifier
            bytes_limit: Data limit in bytes (must be non-negative)

        Returns:
            True if limit was set successfully

        Raises:
            ValueError: If key_id is empty or bytes_limit is negative
            APIError: If key not found or request fails
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        validated_bytes = CommonValidators.validate_non_negative_bytes(bytes_limit)

        request = DataLimitRequest(limit=DataLimit(bytes=validated_bytes))
        response_data = await self.request(
            "PUT",
            f"access-keys/{key_id.strip()}/data-limit",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple_response_data(response_data)

    async def remove_access_key_data_limit(
        self: HTTPClientProtocol, key_id: str
    ) -> bool:
        """
        Remove data transfer limit from access key.

        Args:
            key_id: Access key identifier

        Returns:
            True if limit was removed successfully

        Raises:
            ValueError: If key_id is empty
            APIError: If key not found or request fails
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        response_data = await self.request(
            "DELETE", f"access-keys/{key_id.strip()}/data-limit"
        )
        return ResponseParser.parse_simple_response_data(response_data)


class DataLimitMixin(BaseMixin):
    """Mixin for global data limit operations."""

    async def set_global_data_limit(self: HTTPClientProtocol, bytes_limit: int) -> bool:
        """
        Set global data transfer limit for all access keys.

        Args:
            bytes_limit: Data limit in bytes (must be non-negative)

        Returns:
            True if global limit was set successfully

        Raises:
            ValueError: If bytes_limit is negative
            APIError: If request fails
        """
        validated_bytes = CommonValidators.validate_non_negative_bytes(bytes_limit)

        request = DataLimitRequest(limit=DataLimit(bytes=validated_bytes))
        response_data = await self.request(
            "PUT",
            "server/access-key-data-limit",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple_response_data(response_data)

    async def remove_global_data_limit(self: HTTPClientProtocol) -> bool:
        """
        Remove global data transfer limit.

        Returns:
            True if global limit was removed successfully

        Raises:
            APIError: If request fails
        """
        response_data = await self.request("DELETE", "server/access-key-data-limit")
        return ResponseParser.parse_simple_response_data(response_data)


class BatchProcessor(Generic[T, R]):
    """Generic batch processor for operations with proper error handling."""

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def process_batch(
        self,
        items: list[T],
        processor: Callable[[T], Awaitable[R]],
        fail_fast: bool = False,
    ) -> list[Union[R, Exception]]:
        """
        Process items in batch with concurrency control.

        Args:
            items: Items to process
            processor: Async function to process each item
            fail_fast: Stop on first error if True

        Returns:
            List of results or exceptions
        """

        async def process_single(item: T) -> Union[R, Exception]:
            async with self._semaphore:
                try:
                    return await processor(item)
                except Exception as e:
                    if fail_fast:
                        raise
                    return e

        tasks = [process_single(item) for item in items]
        return await asyncio.gather(*tasks, return_exceptions=not fail_fast)


class BatchOperationsMixin(BaseMixin):
    """Mixin for batch operations with improved type safety and error handling."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._batch_processor = BatchProcessor(max_concurrent=5)

    async def batch_create_access_keys(
        self: HTTPClientProtocol,
        keys_config: list[dict[str, Any]],
        fail_fast: bool = True,
        max_concurrent: int = 5,
    ) -> list[Union[AccessKey, Exception]]:
        """
        Create multiple access keys in batch.

        Args:
            keys_config: List of key configurations (same as create_access_key kwargs)
            fail_fast: If True, stop on first error. If False, continue and return errors.
            max_concurrent: Maximum number of concurrent operations

        Returns:
            List of created keys or exceptions

        Examples:
            Create multiple keys with different configurations::

                configs = [
                    {"name": "User1", "limit": DataLimit(bytes=1024**3)},
                    {"name": "User2", "port": 8388},
                ]
                results = await client.batch_create_access_keys(configs)
        """
        processor = BatchProcessor(max_concurrent)

        async def create_single(config: dict[str, Any]) -> AccessKey:
            result = await self.create_access_key(**config)
            # Ensure we return AccessKey type, not Union
            if isinstance(result, dict):
                # This shouldn't happen in normal operation, but handle it
                raise ValueError("Unexpected JSON response in batch operation")
            return result

        return await processor.process_batch(keys_config, create_single, fail_fast)

    async def batch_delete_access_keys(
        self: HTTPClientProtocol,
        key_ids: list[str],
        fail_fast: bool = False,
        max_concurrent: int = 5,
    ) -> list[Union[bool, Exception]]:
        """
        Delete multiple access keys in batch.

        Args:
            key_ids: List of access key IDs to delete
            fail_fast: If True, stop on first error. If False, continue and return errors.
            max_concurrent: Maximum number of concurrent operations

        Returns:
            List of deletion results (True) or exceptions

        Examples:
            Delete multiple keys::

                key_ids = ["key1", "key2", "key3"]
                results = await client.batch_delete_access_keys(key_ids)
        """
        # Validate all key IDs first
        validated_ids = []
        for key_id in key_ids:
            if not key_id or not key_id.strip():
                if fail_fast:
                    raise ValueError(f"Invalid key_id: '{key_id}'")
                validated_ids.append(
                    key_id
                )  # Let individual operations handle the error
            else:
                validated_ids.append(key_id.strip())

        processor = BatchProcessor(max_concurrent)

        async def delete_single(key_id: str) -> bool:
            return await self.delete_access_key(key_id)

        return await processor.process_batch(validated_ids, delete_single, fail_fast)

    async def batch_rename_access_keys(
        self: HTTPClientProtocol,
        key_name_pairs: list[tuple[str, str]],  # (key_id, new_name)
        fail_fast: bool = False,
        max_concurrent: int = 5,
    ) -> list[Union[bool, Exception]]:
        """
        Rename multiple access keys in batch.

        Args:
            key_name_pairs: List of (key_id, new_name) tuples
            fail_fast: If True, stop on first error. If False, continue and return errors.
            max_concurrent: Maximum number of concurrent operations

        Returns:
            List of rename results (True) or exceptions

        Examples:
            Rename multiple keys::

                pairs = [("key1", "Alice"), ("key2", "Bob"), ("key3", "Charlie")]
                results = await client.batch_rename_access_keys(pairs)
        """
        processor = BatchProcessor(max_concurrent)

        async def rename_single(pair: tuple[str, str]) -> bool:
            key_id, name = pair
            return await self.rename_access_key(key_id, name)

        return await processor.process_batch(key_name_pairs, rename_single, fail_fast)

    async def batch_operations_with_resilience(
        self: HTTPClientProtocol,
        operations: list[tuple[str, str, dict[str, Any]]],  # (method, endpoint, kwargs)
        fail_fast: bool = False,
        max_concurrent: int = 5,
    ) -> list[Union[Any, Exception]]:
        """
        Execute multiple operations with circuit breaker protection and concurrency control.

        Args:
            operations: List of (method, endpoint, kwargs) tuples
            fail_fast: If True, stop on first error. If False, continue and return errors.
            max_concurrent: Maximum number of concurrent operations

        Returns:
            List of results or exceptions

        Examples:
            Execute multiple operations::

                operations = [
                    ("GET", "access-keys/1", {}),
                    ("PUT", "access-keys/2/name", {"json": {"name": "New Name"}}),
                    ("DELETE", "access-keys/3", {}),
                ]
                results = await client.batch_operations_with_resilience(operations)
        """
        processor = BatchProcessor(max_concurrent)

        async def execute_operation(op_data: tuple[str, str, dict[str, Any]]) -> Any:
            method, endpoint, kwargs = op_data
            return await self.request(method, endpoint, **kwargs)

        return await processor.process_batch(operations, execute_operation, fail_fast)
