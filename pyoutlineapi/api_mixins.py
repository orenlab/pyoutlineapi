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

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .audit import AuditDecorator, AuditLogger, get_default_audit_logger
from .common_types import JsonPayload, QueryParams, ResponseData, Validators
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

if TYPE_CHECKING:
    pass


# ===== Mixins for Audit Support =====


class AuditableMixin:
    """Mixin providing audit logger access with singleton fallback."""

    @property
    def _audit_logger(self) -> AuditLogger:
        """Get audit logger with singleton fallback.

        :return: Instance logger if set, otherwise shared default logger
        """
        if hasattr(self, "_audit_logger_instance"):
            return self._audit_logger_instance  # type: ignore[return-value]
        return get_default_audit_logger()


class JsonFormattingMixin:
    """Mixin for handling JSON formatting preferences."""

    def _resolve_json_format(self, as_json: bool | None) -> bool:
        """Resolve JSON format preference using priority: parameter > config > default.

        :param as_json: Explicit format preference
        :return: Resolved format preference
        """
        if as_json is not None:
            return as_json
        return getattr(self, "_default_json_format", False)


# ===== HTTP Client Protocol =====


@runtime_checkable
class HTTPClientProtocol(Protocol):
    """Runtime-checkable protocol for HTTP client.

    Defines minimal interface needed by mixins.
    """

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: JsonPayload = None,
        params: QueryParams | None = None,
    ) -> ResponseData:
        """Internal request method.

        :param method: HTTP method
        :param endpoint: API endpoint
        :param json: Request JSON payload
        :param params: Query parameters
        :return: Response data
        """
        ...


# ===== Server Management Mixin =====


class ServerMixin(AuditableMixin, JsonFormattingMixin):
    """Server management operations.

    API Endpoints (based on OpenAPI schema):
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
        """Get server information and configuration.

        Based on OpenAPI: GET /server

        :param as_json: Return raw JSON instead of model
        :return: Server information
        """
        data = await self._request("GET", "server")
        return ResponseParser.parse(
            data, Server, as_json=self._resolve_json_format(as_json)
        )

    @AuditDecorator.audit_action(
        action="rename_server",
        resource_from=lambda result, *args, **kwargs: "server",
        extract_details=lambda result, *args, **kwargs: {
            "new_name": args[0] if args else "unknown"
        },
    )
    async def rename_server(self: HTTPClientProtocol, name: str) -> bool:
        """Rename the server.

        Based on OpenAPI: PUT /name

        :param name: New server name
        :return: True if successful
        :raises ValueError: If name is empty
        """
        validated_name = Validators.validate_name(name)
        if validated_name is None:
            raise ValueError("Server name cannot be empty")

        request = ServerNameRequest(name=validated_name)
        data = await self._request(
            "PUT", "name", json=request.model_dump(by_alias=True)
        )
        return ResponseParser.parse_simple(data)

    @AuditDecorator.audit_action(
        action="set_hostname",
        resource_from="server",
        extract_details=lambda result, *args, **kwargs: {
            "hostname": args[0] if args else "unknown"
        },
    )
    async def set_hostname(self: HTTPClientProtocol, hostname: str) -> bool:
        """Set hostname for access keys.

        Based on OpenAPI: PUT /server/hostname-for-access-keys

        :param hostname: Hostname to set
        :return: True if successful
        :raises ValueError: If hostname is empty
        """
        if not hostname or not hostname.strip():
            raise ValueError("Hostname cannot be empty")

        request = HostnameRequest(hostname=hostname.strip())
        data = await self._request(
            "PUT",
            "server/hostname-for-access-keys",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    @AuditDecorator.audit_action(
        action="set_default_port",
        resource_from="server",
        extract_details=lambda result, *args, **kwargs: {
            "port": args[0] if args else "unknown"
        },
    )
    async def set_default_port(self: HTTPClientProtocol, port: int) -> bool:
        """Set default port for new access keys.

        Based on OpenAPI: PUT /server/port-for-new-access-keys

        :param port: Port number (1025-65535)
        :return: True if successful
        :raises ValueError: If port is invalid
        """
        validated_port = Validators.validate_port(port)
        request = PortRequest(port=validated_port)
        data = await self._request(
            "PUT",
            "server/port-for-new-access-keys",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)


# ===== Access Key Management Mixin =====


class AccessKeyMixin(AuditableMixin, JsonFormattingMixin):
    """Access key management operations.

    API Endpoints (based on OpenAPI schema):
        - POST /access-keys
        - PUT /access-keys/{id}
        - GET /access-keys
        - GET /access-keys/{id}
        - DELETE /access-keys/{id}
        - PUT /access-keys/{id}/name
        - PUT /access-keys/{id}/data-limit
        - DELETE /access-keys/{id}/data-limit
    """

    @AuditDecorator.audit_action(
        action="create_access_key",
        resource_from="id",
        extract_details=lambda result, *args, **kwargs: {
            "name": kwargs.get("name", "unnamed"),
            "method": kwargs.get("method"),
            "has_limit": kwargs.get("limit") is not None,
        },
    )
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
        """Create new access key with auto-generated ID.

        Based on OpenAPI: POST /access-keys

        :param name: Key name
        :param password: Key password
        :param port: Custom port
        :param method: Encryption method
        :param limit: Data transfer limit
        :param as_json: Return raw JSON instead of model
        :return: Created access key
        """
        validated_name = Validators.validate_name(name) if name is not None else None
        validated_port = Validators.validate_port(port) if port is not None else None

        request = AccessKeyCreateRequest(
            name=validated_name,
            password=password,
            port=validated_port,
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

    @AuditDecorator.audit_action(
        action="create_access_key_with_id",
        resource_from=lambda result, *args, **kwargs: args[0] if args else "unknown",
        extract_details=lambda result, *args, **kwargs: {
            "name": kwargs.get("name", "unnamed"),
            "method": kwargs.get("method"),
            "has_limit": kwargs.get("limit") is not None,
        },
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
        """Create access key with specific ID.

        Based on OpenAPI: PUT /access-keys/{id}

        :param key_id: Desired key ID
        :param name: Key name
        :param password: Key password
        :param port: Custom port
        :param method: Encryption method
        :param limit: Data transfer limit
        :param as_json: Return raw JSON instead of model
        :return: Created access key
        """
        validated_key_id = Validators.validate_key_id(key_id)
        validated_name = Validators.validate_name(name) if name is not None else None
        validated_port = Validators.validate_port(port) if port is not None else None

        request = AccessKeyCreateRequest(
            name=validated_name,
            password=password,
            port=validated_port,
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
        """Get all access keys.

        Based on OpenAPI: GET /access-keys

        :param as_json: Return raw JSON instead of model
        :return: List of access keys
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
        """Get specific access key by ID.

        Based on OpenAPI: GET /access-keys/{id}

        :param key_id: Access key ID
        :param as_json: Return raw JSON instead of model
        :return: Access key details
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request("GET", f"access-keys/{validated_key_id}")
        return ResponseParser.parse(
            data, AccessKey, as_json=self._resolve_json_format(as_json)
        )

    @AuditDecorator.audit_action(
        action="delete_access_key",
        resource_from=lambda result, *args, **kwargs: args[0] if args else "unknown",
        log_failure=True,
    )
    async def delete_access_key(self: HTTPClientProtocol, key_id: str) -> bool:
        """Delete access key.

        Based on OpenAPI: DELETE /access-keys/{id}

        :param key_id: Access key ID to delete
        :return: True if successful
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request("DELETE", f"access-keys/{validated_key_id}")
        return ResponseParser.parse_simple(data)

    @AuditDecorator.audit_action(
        action="rename_access_key",
        resource_from=lambda result, *args, **kwargs: args[0] if args else "unknown",
        extract_details=lambda result, *args, **kwargs: {
            "new_name": args[1] if len(args) > 1 else "unknown"
        },
    )
    async def rename_access_key(
        self: HTTPClientProtocol,
        key_id: str,
        name: str,
    ) -> bool:
        """Rename access key.

        Based on OpenAPI: PUT /access-keys/{id}/name

        :param key_id: Access key ID
        :param name: New name
        :return: True if successful
        :raises ValueError: If name is empty
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

    @AuditDecorator.audit_action(
        action="set_access_key_data_limit",
        resource_from=lambda result, *args, **kwargs: args[0] if args else "unknown",
        extract_details=lambda result, *args, **kwargs: {
            "bytes_limit": args[1] if len(args) > 1 else "unknown"
        },
    )
    async def set_access_key_data_limit(
        self: HTTPClientProtocol,
        key_id: str,
        bytes_limit: int,
    ) -> bool:
        """Set data limit for specific access key.

        Based on OpenAPI: PUT /access-keys/{id}/data-limit

        :param key_id: Access key ID
        :param bytes_limit: Limit in bytes
        :return: True if successful
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

    @AuditDecorator.audit_action(
        action="remove_access_key_data_limit",
        resource_from=lambda result, *args, **kwargs: args[0] if args else "unknown",
    )
    async def remove_access_key_data_limit(
        self: HTTPClientProtocol,
        key_id: str,
    ) -> bool:
        """Remove data limit from access key.

        Based on OpenAPI: DELETE /access-keys/{id}/data-limit

        :param key_id: Access key ID
        :return: True if successful
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request(
            "DELETE", f"access-keys/{validated_key_id}/data-limit"
        )
        return ResponseParser.parse_simple(data)


# ===== Data Limit Mixin =====


class DataLimitMixin(AuditableMixin):
    """Global data limit operations.

    API Endpoints (based on OpenAPI schema):
        - PUT /server/access-key-data-limit
        - DELETE /server/access-key-data-limit
    """

    @AuditDecorator.audit_action(
        action="set_global_data_limit",
        resource_from="server",
        extract_details=lambda result, *args, **kwargs: {
            "bytes_limit": args[0] if args else "unknown"
        },
    )
    async def set_global_data_limit(
        self: HTTPClientProtocol,
        bytes_limit: int,
    ) -> bool:
        """Set global data limit for all access keys.

        Based on OpenAPI: PUT /server/access-key-data-limit

        :param bytes_limit: Limit in bytes
        :return: True if successful
        """
        validated_bytes = Validators.validate_non_negative(bytes_limit, "bytes_limit")
        request = DataLimitRequest(limit=DataLimit(bytes=validated_bytes))

        data = await self._request(
            "PUT",
            "server/access-key-data-limit",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    @AuditDecorator.audit_action(
        action="remove_global_data_limit", resource_from="server"
    )
    async def remove_global_data_limit(self: HTTPClientProtocol) -> bool:
        """Remove global data limit.

        Based on OpenAPI: DELETE /server/access-key-data-limit

        :return: True if successful
        """
        data = await self._request("DELETE", "server/access-key-data-limit")
        return ResponseParser.parse_simple(data)


# ===== Metrics Mixin =====


class MetricsMixin(AuditableMixin, JsonFormattingMixin):
    """Metrics operations.

    API Endpoints (based on OpenAPI schema):
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
        """Get metrics collection status.

        Based on OpenAPI: GET /metrics/enabled

        :param as_json: Return raw JSON instead of model
        :return: Metrics status
        """
        data = await self._request("GET", "metrics/enabled")
        return ResponseParser.parse(
            data, MetricsStatusResponse, as_json=self._resolve_json_format(as_json)
        )

    @AuditDecorator.audit_action(
        action="set_metrics_status",
        resource_from="server",
        extract_details=lambda result, *args, **kwargs: {
            "enabled": args[0] if args else "unknown"
        },
    )
    async def set_metrics_status(self: HTTPClientProtocol, enabled: bool) -> bool:
        """Enable or disable metrics collection.

        Based on OpenAPI: PUT /metrics/enabled

        :param enabled: True to enable, False to disable
        :return: True if successful
        :raises ValueError: If enabled is not boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be bool, got {type(enabled).__name__}")

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
        """Get transfer metrics for all access keys.

        Based on OpenAPI: GET /metrics/transfer

        :param as_json: Return raw JSON instead of model
        :return: Transfer metrics
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
        """Get experimental server metrics.

        Based on OpenAPI: GET /experimental/server/metrics

        :param since: Time period (e.g., '24h', '7d')
        :param as_json: Return raw JSON instead of model
        :return: Experimental metrics
        :raises ValueError: If since parameter is invalid
        """
        if not since or not since.strip():
            raise ValueError("'since' parameter cannot be empty")

        since = since.strip()
        valid_suffixes = {"h", "d", "m", "s"}
        if not any(since.endswith(suffix) for suffix in valid_suffixes):
            raise ValueError(
                f"'since' must end with h/d/m/s (e.g., '24h', '7d'), got: {since}"
            )

        data = await self._request(
            "GET",
            "experimental/server/metrics",
            params={"since": since},
        )
        return ResponseParser.parse(
            data, ExperimentalMetrics, as_json=self._resolve_json_format(as_json)
        )


__all__ = [
    "AccessKeyMixin",
    "AuditableMixin",
    "DataLimitMixin",
    "HTTPClientProtocol",
    "JsonFormattingMixin",
    "MetricsMixin",
    "ServerMixin",
]
