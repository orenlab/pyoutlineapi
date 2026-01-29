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

from functools import cached_property
from typing import TYPE_CHECKING, Any, Final, cast

from pydantic import Field, field_validator

from .common_types import (
    BaseValidatedModel,
    Bytes,
    BytesPerUserDict,
    ChecksDict,
    Port,
    TimestampMs,
    TimestampSec,
    Validators,
)

if TYPE_CHECKING:
    from typing_extensions import Self

# Constants for unit conversions (immutable, typed)
_BYTES_IN_KB: Final[int] = 1024
_BYTES_IN_MB: Final[int] = 1024**2
_BYTES_IN_GB: Final[int] = 1024**3
_MS_IN_SEC: Final[float] = 1000.0
_SEC_IN_MIN: Final[float] = 60.0
_SEC_IN_HOUR: Final[float] = 3600.0


# ===== Unit Conversion Mixins =====


class ByteConversionMixin:
    """Mixin for byte conversion utilities with optimized calculations."""

    bytes: int

    @property
    def kilobytes(self) -> float:
        """Get value in kilobytes.

        :return: Value in KB
        """
        return self.bytes / _BYTES_IN_KB

    @property
    def megabytes(self) -> float:
        """Get value in megabytes.

        :return: Value in MB
        """
        return self.bytes / _BYTES_IN_MB

    @property
    def gigabytes(self) -> float:
        """Get value in gigabytes.

        :return: Value in GB
        """
        return self.bytes / _BYTES_IN_GB


class TimeConversionMixin:
    """Mixin for time conversion utilities with optimized calculations."""

    seconds: int

    @property
    def minutes(self) -> float:
        """Get time in minutes.

        :return: Time in minutes
        """
        return self.seconds / _SEC_IN_MIN

    @property
    def hours(self) -> float:
        """Get time in hours.

        :return: Time in hours
        """
        return self.seconds / _SEC_IN_HOUR


# ===== Core Models =====


class DataLimit(BaseValidatedModel, ByteConversionMixin):
    """Data transfer limit in bytes with unit conversions."""

    bytes: Bytes

    @classmethod
    def from_kilobytes(cls, kb: float) -> Self:
        """Create DataLimit from kilobytes.

        :param kb: Size in kilobytes
        :return: DataLimit instance
        """
        return cls(bytes=int(kb * _BYTES_IN_KB))

    @classmethod
    def from_megabytes(cls, mb: float) -> Self:
        """Create DataLimit from megabytes.

        :param mb: Size in megabytes
        :return: DataLimit instance
        """
        return cls(bytes=int(mb * _BYTES_IN_MB))

    @classmethod
    def from_gigabytes(cls, gb: float) -> Self:
        """Create DataLimit from gigabytes.

        :param gb: Size in gigabytes
        :return: DataLimit instance
        """
        return cls(bytes=int(gb * _BYTES_IN_GB))


class AccessKey(BaseValidatedModel):
    """Access key model matching API schema with optimized properties.

    SCHEMA: Based on OpenAPI /access-keys endpoint
    """

    id: str
    name: str | None = None
    password: str
    port: Port
    method: str
    access_url: str = Field(alias="accessUrl")
    data_limit: DataLimit | None = Field(None, alias="dataLimit")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Handle empty names from API.

        :param v: Name value
        :return: Validated name or None
        """
        if v is None:
            return None
        return Validators.validate_name(v)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate key ID.

        :param v: Key ID
        :return: Validated key ID
        :raises ValueError: If ID is invalid
        """
        return Validators.validate_key_id(v)

    @property
    def has_data_limit(self) -> bool:
        """Check if key has data limit (optimized None check).

        :return: True if data limit exists
        """
        return self.data_limit is not None

    @property
    def display_name(self) -> str:
        """Get display name with optimized conditional.

        :return: Display name
        """
        return self.name if self.name else f"Key-{self.id}"


class AccessKeyList(BaseValidatedModel):
    """List of access keys with optimized utility methods.

    SCHEMA: Based on GET /access-keys response
    """

    access_keys: list[AccessKey] = Field(alias="accessKeys")

    @cached_property
    def count(self) -> int:
        """Get number of access keys (cached).

        NOTE: Cached because list is immutable after creation

        :return: Key count
        """
        return len(self.access_keys)

    @property
    def is_empty(self) -> bool:
        """Check if list is empty (uses cached count).

        :return: True if no keys
        """
        return self.count == 0

    def get_by_id(self, key_id: str) -> AccessKey | None:
        """Get key by ID with early return optimization.

        :param key_id: Access key ID
        :return: Access key or None if not found
        """
        for key in self.access_keys:
            if key.id == key_id:
                return key
        return None

    def get_by_name(self, name: str) -> list[AccessKey]:
        """Get keys by name with optimized list comprehension.

        :param name: Key name
        :return: List of matching keys (may be multiple)
        """
        return [key for key in self.access_keys if key.name == name]

    def filter_with_limits(self) -> list[AccessKey]:
        """Get keys with data limits (optimized comprehension).

        :return: List of keys with limits
        """
        return [key for key in self.access_keys if key.has_data_limit]

    def filter_without_limits(self) -> list[AccessKey]:
        """Get keys without data limits (optimized comprehension).

        :return: List of keys without limits
        """
        return [key for key in self.access_keys if not key.has_data_limit]


class Server(BaseValidatedModel):
    """Server information model with optimized properties.

    SCHEMA: Based on GET /server response
    """

    name: str | None = None
    server_id: str = Field(alias="serverId")
    metrics_enabled: bool = Field(alias="metricsEnabled")
    created_timestamp_ms: TimestampMs = Field(alias="createdTimestampMs")
    port_for_new_access_keys: Port = Field(alias="portForNewAccessKeys")
    hostname_for_access_keys: str | None = Field(None, alias="hostnameForAccessKeys")
    access_key_data_limit: DataLimit | None = Field(None, alias="accessKeyDataLimit")
    version: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate server name.

        :param v: Server name
        :return: Validated name
        :raises ValueError: If name is empty
        """
        validated = Validators.validate_name(v)
        if validated is None:
            raise ValueError("Server name cannot be empty")
        return validated

    @property
    def has_global_limit(self) -> bool:
        """Check if server has global data limit (optimized).

        :return: True if global limit exists
        """
        return self.access_key_data_limit is not None

    @cached_property
    def created_timestamp_seconds(self) -> float:
        """Get creation timestamp in seconds (cached).

        NOTE: Cached because timestamp is immutable

        :return: Timestamp in seconds
        """
        return self.created_timestamp_ms / _MS_IN_SEC


# ===== Metrics Models =====


class ServerMetrics(BaseValidatedModel):
    """Transfer metrics with optimized aggregations.

    SCHEMA: Based on GET /metrics/transfer response
    """

    bytes_transferred_by_user_id: BytesPerUserDict = Field(
        alias="bytesTransferredByUserId"
    )

    @cached_property
    def total_bytes(self) -> int:
        """Calculate total bytes with caching.

        :return: Total bytes transferred
        """
        return sum(self.bytes_transferred_by_user_id.values())

    @cached_property
    def total_gigabytes(self) -> float:
        """Get total in gigabytes (uses cached total_bytes).

        :return: Total GB transferred
        """
        return self.total_bytes / _BYTES_IN_GB

    @cached_property
    def user_count(self) -> int:
        """Get number of users (cached).

        :return: Number of users
        """
        return len(self.bytes_transferred_by_user_id)

    def get_user_bytes(self, user_id: str) -> int:
        """Get bytes for specific user (O(1) dict lookup).

        :param user_id: User/key ID
        :return: Bytes transferred or 0 if not found
        """
        return self.bytes_transferred_by_user_id.get(user_id, 0)

    def top_users(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get top users by bytes transferred (optimized sorting).

        :param limit: Number of top users to return
        :return: List of (user_id, bytes) tuples
        """
        return sorted(
            self.bytes_transferred_by_user_id.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:limit]


class TunnelTime(BaseValidatedModel, TimeConversionMixin):
    """Tunnel time metric with time conversions.

    SCHEMA: Based on experimental metrics tunnelTime object
    """

    seconds: int = Field(ge=0)


class DataTransferred(BaseValidatedModel, ByteConversionMixin):
    """Data transfer metric with byte conversions.

    SCHEMA: Based on experimental metrics dataTransferred object
    """

    bytes: Bytes


class BandwidthDataValue(BaseValidatedModel):
    """Bandwidth data value.

    SCHEMA: Based on experimental metrics bandwidth data object
    """

    bytes: int


class BandwidthData(BaseValidatedModel):
    """Bandwidth measurement data.

    SCHEMA: Based on experimental metrics bandwidth current/peak object
    """

    data: BandwidthDataValue
    timestamp: TimestampSec | None = None


class BandwidthInfo(BaseValidatedModel):
    """Current and peak bandwidth information.

    SCHEMA: Based on experimental metrics bandwidth object
    """

    current: BandwidthData
    peak: BandwidthData


class LocationMetric(BaseValidatedModel):
    """Location-based usage metric.

    SCHEMA: Based on experimental metrics locations array item
    """

    location: str
    asn: int | None = None
    as_org: str | None = Field(None, alias="asOrg")
    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")


class PeakDeviceCount(BaseValidatedModel):
    """Peak device count with timestamp.

    SCHEMA: Based on experimental metrics connection peakDeviceCount object
    """

    data: int
    timestamp: TimestampSec


class ConnectionInfo(BaseValidatedModel):
    """Connection information and statistics.

    SCHEMA: Based on experimental metrics connection object
    """

    last_traffic_seen: TimestampSec = Field(alias="lastTrafficSeen")
    peak_device_count: PeakDeviceCount = Field(alias="peakDeviceCount")


class AccessKeyMetric(BaseValidatedModel):
    """Per-key experimental metrics.

    SCHEMA: Based on experimental metrics accessKeys array item
    """

    access_key_id: str = Field(alias="accessKeyId")
    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    connection: ConnectionInfo


class ServerExperimentalMetric(BaseValidatedModel):
    """Server-level experimental metrics.

    SCHEMA: Based on experimental metrics server object
    """

    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    bandwidth: BandwidthInfo
    locations: list[LocationMetric]


class ExperimentalMetrics(BaseValidatedModel):
    """Experimental metrics with optimized lookup.

    SCHEMA: Based on GET /experimental/server/metrics response
    """

    server: ServerExperimentalMetric
    access_keys: list[AccessKeyMetric] = Field(alias="accessKeys")

    def get_key_metric(self, key_id: str) -> AccessKeyMetric | None:
        """Get metrics for specific key with early return.

        :param key_id: Access key ID
        :return: Key metrics or None if not found
        """
        for metric in self.access_keys:
            if metric.access_key_id == key_id:
                return metric  # Early return
        return None


# ===== Request Models =====


class AccessKeyCreateRequest(BaseValidatedModel):
    """Request model for creating access keys.

    SCHEMA: Based on POST /access-keys request body
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    method: str | None = None
    password: str | None = None
    port: Port | None = None
    limit: DataLimit | None = None


class ServerNameRequest(BaseValidatedModel):
    """Request model for renaming server.

    SCHEMA: Based on PUT /name request body
    """

    name: str = Field(min_length=1, max_length=255)


class HostnameRequest(BaseValidatedModel):
    """Request model for setting hostname.

    SCHEMA: Based on PUT /server/hostname-for-access-keys request body
    """

    hostname: str = Field(min_length=1)


class PortRequest(BaseValidatedModel):
    """Request model for setting default port.

    SCHEMA: Based on PUT /server/port-for-new-access-keys request body
    """

    port: Port


class AccessKeyNameRequest(BaseValidatedModel):
    """Request model for renaming access key.

    SCHEMA: Based on PUT /access-keys/{id}/name request body
    """

    name: str = Field(min_length=1, max_length=255)


class DataLimitRequest(BaseValidatedModel):
    """Request model for setting data limit.

    Note:
        The API expects the DataLimit object directly.
        Use to_payload() to produce the correct request body.
    """

    limit: DataLimit

    def to_payload(self) -> dict[str, int]:
        """Convert to API request payload.

        :return: Payload dict with bytes field
        """
        return cast(dict[str, int], self.limit.model_dump(by_alias=True))


class MetricsEnabledRequest(BaseValidatedModel):
    """Request model for enabling/disabling metrics.

    SCHEMA: Based on PUT /metrics/enabled request body
    """

    metrics_enabled: bool = Field(alias="metricsEnabled")


class MetricsStatusResponse(BaseValidatedModel):
    """Response model for metrics status.

    Returns current metrics sharing status.
    SCHEMA: Based on GET /metrics/enabled response
    """

    metrics_enabled: bool = Field(alias="metricsEnabled")


# ===== Response Models =====


class ErrorResponse(BaseValidatedModel):
    """Error response with optimized string formatting.

    SCHEMA: Based on API error response format
    """

    code: str
    message: str

    def __str__(self) -> str:
        """Format error as string (optimized f-string).

        :return: Formatted error message
        """
        return f"{self.code}: {self.message}"


# ===== Utility Models =====


class HealthCheckResult(BaseValidatedModel):
    """Health check result with optimized diagnostics."""

    healthy: bool
    timestamp: float
    checks: ChecksDict

    @cached_property
    def failed_checks(self) -> list[str]:
        """Get failed checks (cached for repeated access).

        :return: List of failed check names
        """
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") != "healthy"
        ]

    @property
    def success_rate(self) -> float:
        """Calculate success rate (uses cached failed_checks).

        :return: Success rate (0.0 to 1.0)
        """
        if not self.checks:
            return 1.0  # Early return

        total = len(self.checks)
        passed = total - len(self.failed_checks)  # Uses cached property
        return passed / total


class ServerSummary(BaseValidatedModel):
    """Server summary with optimized aggregations."""

    server: dict[str, Any]
    access_keys_count: int
    healthy: bool
    transfer_metrics: BytesPerUserDict | None = None
    experimental_metrics: dict[str, Any] | None = None
    error: str | None = None

    @property
    def total_bytes_transferred(self) -> int:
        """Get total bytes with early return optimization.

        :return: Total bytes or 0 if no metrics
        """
        if not self.transfer_metrics:
            return 0  # Early return
        return sum(self.transfer_metrics.values())

    @property
    def total_gigabytes_transferred(self) -> float:
        """Get total GB (uses total_bytes_transferred).

        :return: Total GB or 0.0 if no metrics
        """
        return self.total_bytes_transferred / _BYTES_IN_GB

    @property
    def has_errors(self) -> bool:
        """Check if summary has errors (optimized None check).

        :return: True if errors present
        """
        return self.error is not None


__all__ = [
    "AccessKey",
    "AccessKeyCreateRequest",
    "AccessKeyList",
    "AccessKeyMetric",
    "AccessKeyNameRequest",
    "BandwidthData",
    "BandwidthDataValue",
    "BandwidthInfo",
    "ConnectionInfo",
    "DataLimit",
    "DataLimitRequest",
    "DataTransferred",
    "ErrorResponse",
    "ExperimentalMetrics",
    "HealthCheckResult",
    "HostnameRequest",
    "LocationMetric",
    "MetricsEnabledRequest",
    "MetricsStatusResponse",
    "PeakDeviceCount",
    "PortRequest",
    "Server",
    "ServerExperimentalMetric",
    "ServerMetrics",
    "ServerNameRequest",
    "ServerSummary",
    "TunnelTime",
]
