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

from typing import Protocol, runtime_checkable

from .audit import AuditLogger, audited, get_or_create_audit_logger
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

# ===== Mixins for Audit Support =====


class AuditableMixin:
    """Mixin providing audit logger access with singleton fallback."""

    @property
    def _audit_logger(self) -> AuditLogger:
        """Get audit logger with singleton fallback.

        :return: Instance logger if set, otherwise shared default logger
        """
        instance_dict = self.__dict__
        if "_audit_logger_instance" in instance_dict:
            return instance_dict["_audit_logger_instance"]
        return get_or_create_audit_logger()


class JsonFormattingMixin:
    """Mixin for handling JSON formatting preferences."""

    def _resolve_json_format(self, as_json: bool | None) -> bool:
        """Resolve JSON format preference using priority: parameter > config > default.

        :param as_json: Explicit format preference
        :return: Resolved format preference
        """
        if as_json is not None:
            return as_json
        # Use getattr with default to avoid AttributeError overhead
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

    def _resolve_json_format(self, as_json: bool | None) -> bool:
        """Resolve JSON format preference.

        :param as_json: Explicit format preference
        :return: Resolved format preference
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

    __slots__ = ()

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

    @audited()
    async def rename_server(self: HTTPClientProtocol, name: str) -> bool:
        """Rename the server.

        Based on OpenAPI: PUT /name

        :param name: New server name
        :return: True if successful
        :raises ValueError: If name is empty
        """
        validated_name = Validators.validate_name(name)
        if validated_name is None:
            msg = "Server name cannot be empty"
            raise ValueError(msg)

        request = ServerNameRequest(name=validated_name)
        data = await self._request(
            "PUT", "name", json=request.model_dump(by_alias=True)
        )
        return ResponseParser.parse_simple(data)

    @audited()
    async def set_hostname(self: HTTPClientProtocol, hostname: str) -> bool:
        """Set hostname for access keys.

        Based on OpenAPI: PUT /server/hostname-for-access-keys

        :param hostname: Hostname to set
        :return: True if successful
        :raises ValueError: If hostname is empty
        """
        if not hostname or not hostname.strip():
            msg = "Hostname cannot be empty"
            raise ValueError(msg)

        sanitized_hostname = hostname.strip()
        request = HostnameRequest(hostname=sanitized_hostname)

        data = await self._request(
            "PUT",
            "server/hostname-for-access-keys",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    @audited()
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

    __slots__ = ()

    @audited()
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

        payload = request.model_dump(by_alias=True, exclude_none=True)
        data = await self._request("POST", "access-keys", json=payload)

        return ResponseParser.parse(
            data, AccessKey, as_json=self._resolve_json_format(as_json)
        )

    @audited()
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
        """Create new access key with specific ID.

        Based on OpenAPI: PUT /access-keys/{id}

        :param key_id: Desired access key ID
        :param name: Key name
        :param password: Key password
        :param port: Custom port
        :param method: Encryption method
        :param limit: Data transfer limit
        :param as_json: Return raw JSON instead of model
        :return: Created access key
        :raises ValueError: If key_id is invalid
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

        payload = request.model_dump(by_alias=True, exclude_none=True)
        data = await self._request(
            "PUT", f"access-keys/{validated_key_id}", json=payload
        )

        return ResponseParser.parse(
            data, AccessKey, as_json=self._resolve_json_format(as_json)
        )

    async def get_access_keys(
        self: HTTPClientProtocol,
        *,
        as_json: bool | None = None,
    ) -> AccessKeyList | JsonDict:
        """Get list of all access keys.

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
        :return: Access key
        :raises ValueError: If key_id is invalid
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request("GET", f"access-keys/{validated_key_id}")
        return ResponseParser.parse(
            data, AccessKey, as_json=self._resolve_json_format(as_json)
        )

    @audited()
    async def delete_access_key(self: HTTPClientProtocol, key_id: str) -> bool:
        """Delete access key.

        Based on OpenAPI: DELETE /access-keys/{id}

        :param key_id: Access key ID
        :return: True if successful
        :raises ValueError: If key_id is invalid
        """
        validated_key_id = Validators.validate_key_id(key_id)

        data = await self._request("DELETE", f"access-keys/{validated_key_id}")
        return ResponseParser.parse_simple(data)

    @audited()
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
        :raises ValueError: If key_id or name is invalid
        """
        validated_key_id = Validators.validate_key_id(key_id)
        validated_name = Validators.validate_name(name)

        if validated_name is None:
            msg = "Name cannot be empty"
            raise ValueError(msg)

        request = AccessKeyNameRequest(name=validated_name)
        data = await self._request(
            "PUT",
            f"access-keys/{validated_key_id}/name",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    @audited()
    async def set_access_key_data_limit(
        self: HTTPClientProtocol,
        key_id: str,
        limit: DataLimit,
    ) -> bool:
        """Set data limit for specific access key.

        Based on OpenAPI: PUT /access-keys/{id}/data-limit

        :param key_id: Access key ID
        :param limit: Data transfer limit
        :return: True if successful
        :raises ValueError: If key_id is invalid
        """
        validated_key_id = Validators.validate_key_id(key_id)

        request = DataLimitRequest(limit=limit)

        data = await self._request(
            "PUT",
            f"access-keys/{validated_key_id}/data-limit",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    @audited()
    async def remove_access_key_data_limit(
        self: HTTPClientProtocol,
        key_id: str,
    ) -> bool:
        """Remove data limit from access key.

        Based on OpenAPI: DELETE /access-keys/{id}/data-limit

        :param key_id: Access key ID
        :return: True if successful
        :raises ValueError: If key_id is invalid
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

    __slots__ = ()

    @audited()
    async def set_global_data_limit(
        self: HTTPClientProtocol,
        limit: DataLimit,
    ) -> bool:
        """Set global data limit for all access keys.

        Based on OpenAPI: PUT /server/access-key-data-limit

        :param limit: Data transfer limit
        :return: True if successful
        """
        request = DataLimitRequest(limit=limit)

        data = await self._request(
            "PUT",
            "server/access-key-data-limit",
            json=request.model_dump(by_alias=True),
        )
        return ResponseParser.parse_simple(data)

    @audited()
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

    __slots__ = ()

    _VALID_SINCE_SUFFIXES: frozenset[str] = frozenset({"h", "d", "m", "s"})

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

    @audited()
    async def set_metrics_status(self: HTTPClientProtocol, enabled: bool) -> bool:
        """Enable or disable metrics collection.

        Based on OpenAPI: PUT /metrics/enabled

        :param enabled: True to enable, False to disable
        :return: True if successful
        :raises ValueError: If enabled is not boolean
        """
        if not isinstance(enabled, bool):
            msg = f"enabled must be bool, got {type(enabled).__name__}"
            raise ValueError(msg)

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
            msg = "'since' parameter cannot be empty"
            raise ValueError(msg)

        sanitized_since = since.strip()

        if sanitized_since[-1] not in self._VALID_SINCE_SUFFIXES:
            msg = (
                f"'since' must end with h/d/m/s (e.g., '24h', '7d'), "
                f"got: {sanitized_since}"
            )
            raise ValueError(msg)

        data = await self._request(
            "GET",
            "experimental/server/metrics",
            params={"since": sanitized_since},
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
