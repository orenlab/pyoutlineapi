"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Data models matching Outline API v1.0 schema.

All models are validated Pydantic models that match the official
Outline VPN Server API schema. They provide type safety and automatic
validation for all API interactions.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .common_types import BaseValidatedModel, Bytes, Port, Timestamp, Validators


# ===== Core Models =====


class DataLimit(BaseValidatedModel):
    """
    Data transfer limit in bytes.

    Used for both per-key and global data limits.

    Example:
        >>> from pyoutlineapi.models import DataLimit
        >>> limit = DataLimit(bytes=5 * 1024**3)  # 5 GB
        >>> print(f"Limit: {limit.bytes / 1024**3:.2f} GB")
    """

    bytes: Bytes = Field(description="Data limit in bytes", ge=0)


class AccessKey(BaseValidatedModel):
    """
    Access key model (matches API schema).

    Represents a single VPN access key with all its properties.

    Attributes:
        id: Access key identifier
        name: Optional key name
        password: Key password for connection
        port: Port number (1025-65535)
        method: Encryption method (e.g., "chacha20-ietf-poly1305")
        access_url: Shadowsocks connection URL
        data_limit: Optional per-key data limit

    Example:
        >>> key = await client.create_access_key(name="Alice")
        >>> print(f"Key ID: {key.id}")
        >>> print(f"Name: {key.name}")
        >>> print(f"URL: {key.access_url}")
        >>> if key.data_limit:
        ...     print(f"Limit: {key.data_limit.bytes} bytes")
    """

    id: str = Field(description="Access key identifier")
    name: str | None = Field(None, description="Access key name")
    password: str = Field(description="Access key password")
    port: Port = Field(description="Port number")
    method: str = Field(description="Encryption method")
    access_url: str = Field(
        alias="accessUrl",
        description="Shadowsocks URL",
    )
    data_limit: DataLimit | None = Field(
        None,
        alias="dataLimit",
        description="Per-key data limit",
    )

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Handle empty names from API."""
        return Validators.validate_name(v)


class AccessKeyList(BaseValidatedModel):
    """
    List of access keys (matches API schema).

    Container for multiple access keys with convenience properties.

    Attributes:
        access_keys: List of access key objects

    Example:
        >>> keys = await client.get_access_keys()
        >>> print(f"Total keys: {keys.count}")
        >>> for key in keys.access_keys:
        ...     print(f"- {key.name}: {key.id}")
    """

    access_keys: list[AccessKey] = Field(
        alias="accessKeys",
        description="Access keys array",
    )

    @property
    def count(self) -> int:
        """
        Get number of access keys.

        Returns:
            int: Number of keys in the list

        Example:
            >>> keys = await client.get_access_keys()
            >>> print(f"You have {keys.count} keys")
        """
        return len(self.access_keys)


class Server(BaseValidatedModel):
    """
    Server information model (matches API schema).

    Contains complete server configuration and metadata.

    Attributes:
        name: Server name
        server_id: Server unique identifier
        metrics_enabled: Whether metrics sharing is enabled
        created_timestamp_ms: Server creation timestamp (milliseconds)
        port_for_new_access_keys: Default port for new keys
        hostname_for_access_keys: Hostname used in access keys
        access_key_data_limit: Global data limit for all keys
        version: Server version string

    Example:
        >>> server = await client.get_server_info()
        >>> print(f"Server: {server.name}")
        >>> print(f"ID: {server.server_id}")
        >>> print(f"Port: {server.port_for_new_access_keys}")
        >>> print(f"Hostname: {server.hostname_for_access_keys}")
        >>> if server.access_key_data_limit:
        ...     gb = server.access_key_data_limit.bytes / 1024**3
        ...     print(f"Global limit: {gb:.2f} GB")
    """

    name: str = Field(description="Server name")
    server_id: str = Field(alias="serverId", description="Server identifier")
    metrics_enabled: bool = Field(
        alias="metricsEnabled",
        description="Metrics sharing status",
    )
    created_timestamp_ms: Timestamp = Field(
        alias="createdTimestampMs",
        description="Creation timestamp (ms)",
    )
    port_for_new_access_keys: Port = Field(
        alias="portForNewAccessKeys",
        description="Default port for new keys",
    )
    hostname_for_access_keys: str | None = Field(
        None,
        alias="hostnameForAccessKeys",
        description="Hostname for keys",
    )
    access_key_data_limit: DataLimit | None = Field(
        None,
        alias="accessKeyDataLimit",
        description="Global data limit",
    )
    version: str | None = Field(None, description="Server version")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate server name."""
        validated = Validators.validate_name(v)
        if validated is None:
            raise ValueError("Server name cannot be empty")
        return validated


# ===== Metrics Models =====


class ServerMetrics(BaseValidatedModel):
    """
    Transfer metrics model (matches API /metrics/transfer).

    Contains data transfer statistics for all access keys.

    Attributes:
        bytes_transferred_by_user_id: Dictionary mapping key IDs to bytes transferred

    Example:
        >>> metrics = await client.get_transfer_metrics()
        >>> print(f"Total bytes: {metrics.total_bytes}")
        >>> for key_id, bytes_used in metrics.bytes_transferred_by_user_id.items():
        ...     mb = bytes_used / 1024**2
        ...     print(f"Key {key_id}: {mb:.2f} MB")
    """

    bytes_transferred_by_user_id: dict[str, int] = Field(
        alias="bytesTransferredByUserId",
        description="Bytes per access key ID",
    )

    @property
    def total_bytes(self) -> int:
        """
        Calculate total bytes across all keys.

        Returns:
            int: Total bytes transferred

        Example:
            >>> metrics = await client.get_transfer_metrics()
            >>> gb = metrics.total_bytes / 1024**3
            >>> print(f"Total: {gb:.2f} GB")
        """
        return sum(self.bytes_transferred_by_user_id.values())


class MetricsStatusResponse(BaseValidatedModel):
    """
    Metrics status response (matches API /metrics/enabled).

    Indicates whether metrics collection is enabled.

    Example:
        >>> status = await client.get_metrics_status()
        >>> if status.metrics_enabled:
        ...     print("Metrics are enabled")
        ...     metrics = await client.get_transfer_metrics()
    """

    metrics_enabled: bool = Field(
        alias="metricsEnabled",
        description="Metrics status",
    )


# ===== Experimental Metrics Models =====


class TunnelTime(BaseValidatedModel):
    """Tunnel time metric in seconds."""

    seconds: int = Field(ge=0, description="Seconds")


class DataTransferred(BaseValidatedModel):
    """Data transfer metric in bytes."""

    bytes: Bytes = Field(description="Bytes transferred")


class BandwidthData(BaseValidatedModel):
    """Bandwidth measurement data."""

    data: dict[str, int] = Field(description="Bandwidth data")
    timestamp: Timestamp | None = Field(None, description="Timestamp")


class BandwidthInfo(BaseValidatedModel):
    """Current and peak bandwidth information."""

    current: BandwidthData
    peak: BandwidthData


class LocationMetric(BaseValidatedModel):
    """Location-based usage metric."""

    location: str
    asn: int | None = None
    as_org: str | None = Field(None, alias="asOrg")
    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")


class ConnectionInfo(BaseValidatedModel):
    """Connection information and statistics."""

    last_traffic_seen: Timestamp = Field(alias="lastTrafficSeen")
    peak_device_count: dict[str, int | Timestamp] = Field(alias="peakDeviceCount")


class AccessKeyMetric(BaseValidatedModel):
    """Per-key experimental metrics."""

    access_key_id: str = Field(alias="accessKeyId")
    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    connection: ConnectionInfo


class ServerExperimentalMetric(BaseValidatedModel):
    """Server-level experimental metrics."""

    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    bandwidth: BandwidthInfo
    locations: list[LocationMetric]


class ExperimentalMetrics(BaseValidatedModel):
    """
    Experimental metrics response (matches API /experimental/server/metrics).

    Contains advanced server and per-key metrics.

    Example:
        >>> metrics = await client.get_experimental_metrics("24h")
        >>> print(f"Server data: {metrics.server.data_transferred.bytes}")
        >>> print(f"Locations: {len(metrics.server.locations)}")
        >>> for key_metric in metrics.access_keys:
        ...     print(f"Key {key_metric.access_key_id}: "
        ...           f"{key_metric.data_transferred.bytes} bytes")
    """

    server: ServerExperimentalMetric
    access_keys: list[AccessKeyMetric] = Field(alias="accessKeys")


# ===== Request Models =====


class AccessKeyCreateRequest(BaseValidatedModel):
    """
    Request model for creating access keys.

    All fields are optional; the server will generate defaults.

    Example:
        >>> # Used internally by client.create_access_key()
        >>> request = AccessKeyCreateRequest(
        ...     name="Alice",
        ...     port=8388,
        ...     limit=DataLimit(bytes=5 * 1024**3),
        ... )
    """

    name: str | None = None
    method: str | None = None
    password: str | None = None
    port: Port | None = None
    limit: DataLimit | None = None


class ServerNameRequest(BaseValidatedModel):
    """Request model for renaming server."""

    name: str = Field(min_length=1, max_length=255)


class HostnameRequest(BaseValidatedModel):
    """Request model for setting hostname."""

    hostname: str = Field(min_length=1)


class PortRequest(BaseValidatedModel):
    """Request model for setting default port."""

    port: Port


class AccessKeyNameRequest(BaseValidatedModel):
    """Request model for renaming access key."""

    name: str = Field(min_length=1, max_length=255)


class DataLimitRequest(BaseValidatedModel):
    """Request model for setting data limit."""

    limit: DataLimit


class MetricsEnabledRequest(BaseValidatedModel):
    """Request model for enabling/disabling metrics."""

    metrics_enabled: bool = Field(alias="metricsEnabled")


# ===== Response Models =====


class ErrorResponse(BaseValidatedModel):
    """
    Error response model (matches API error schema).

    Represents errors returned by the API.

    Example:
        >>> # Usually raised as APIError exception
        >>> try:
        ...     await client.get_access_key("invalid-id")
        ... except APIError as e:
        ...     print(f"Error: {e.status_code} - {e}")
    """

    code: str = Field(description="Error code")
    message: str = Field(description="Error message")

    def __str__(self) -> str:
        """Format error as string."""
        return f"{self.code}: {self.message}"


# ===== Utility Models =====


class HealthCheckResult(BaseValidatedModel):
    """
    Health check result (custom utility model).

    Used by health monitoring addon.

    Note: Structure not strictly typed as it depends on custom checks.
    Will be properly typed with TypedDict in future version.

    Example:
        >>> # Used by HealthMonitor
        >>> health = await client.health_check()
        >>> print(f"Healthy: {health['healthy']}")
    """

    healthy: bool
    timestamp: float
    checks: dict[str, dict[str, Any]]


class ServerSummary(BaseValidatedModel):
    """
    Server summary model (custom utility model).

    Aggregates server info, key count, and metrics in one response.

    Note: Contains flexible dict fields for varying metric structures.
    Will be properly typed with TypedDict in future version.

    Example:
        >>> summary = await client.get_server_summary()
        >>> print(f"Server: {summary.server['name']}")
        >>> print(f"Keys: {summary.access_keys_count}")
        >>> if summary.transfer_metrics:
        ...     total = sum(summary.transfer_metrics.values())
        ...     print(f"Total bytes: {total}")
    """

    server: dict[str, Any]
    access_keys_count: int
    healthy: bool
    transfer_metrics: dict[str, int] | None = None
    experimental_metrics: dict[str, Any] | None = None
    error: str | None = None


__all__ = [
    # Core
    "DataLimit",
    "AccessKey",
    "AccessKeyList",
    "Server",
    # Metrics
    "ServerMetrics",
    "MetricsStatusResponse",
    "ExperimentalMetrics",
    # Requests
    "AccessKeyCreateRequest",
    "ServerNameRequest",
    "HostnameRequest",
    "PortRequest",
    "AccessKeyNameRequest",
    "DataLimitRequest",
    "MetricsEnabledRequest",
    # Responses
    "ErrorResponse",
    # Utility
    "HealthCheckResult",
    "ServerSummary",
]
