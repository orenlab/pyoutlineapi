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

from typing import TYPE_CHECKING, Any, Final

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

# Constants for unit conversions
_BYTES_IN_KB: Final[int] = 1024
_BYTES_IN_MB: Final[int] = 1024**2
_BYTES_IN_GB: Final[int] = 1024**3
_MS_IN_SEC: Final[float] = 1000.0
_SEC_IN_MIN: Final[float] = 60.0
_SEC_IN_HOUR: Final[float] = 3600.0


# ===== Unit Conversion Mixin =====


class ByteConversionMixin:
    """Mixin for byte conversion utilities (DRY)."""

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
    """Mixin for time conversion utilities (DRY)."""

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
    """Data transfer limit in bytes.

    Provides convenient unit conversions and factory methods.
    """

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
    """Access key model matching API schema.

    Represents a VPN access key with authentication and configuration details.
    Based on OpenAPI schema: /access-keys endpoint
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
        """Check if key has data limit set.

        :return: True if data limit exists
        """
        return self.data_limit is not None

    @property
    def display_name(self) -> str:
        """Get display name (name or id if no name).

        :return: Display name
        """
        return self.name if self.name else f"Key-{self.id}"


class AccessKeyList(BaseValidatedModel):
    """List of access keys with utility methods.

    Provides convenient access and filtering operations.
    Based on OpenAPI schema: GET /access-keys response
    """

    access_keys: list[AccessKey] = Field(alias="accessKeys")

    @property
    def count(self) -> int:
        """Get number of access keys.

        :return: Key count
        """
        return len(self.access_keys)

    @property
    def is_empty(self) -> bool:
        """Check if list is empty.

        :return: True if no keys
        """
        return self.count == 0

    def get_by_id(self, key_id: str) -> AccessKey | None:
        """Get key by ID.

        :param key_id: Access key ID
        :return: Access key or None if not found
        """
        for key in self.access_keys:
            if key.id == key_id:
                return key
        return None

    def get_by_name(self, name: str) -> list[AccessKey]:
        """Get keys by name.

        May return multiple keys with the same name.

        :param name: Key name
        :return: List of matching keys
        """
        return [key for key in self.access_keys if key.name == name]

    def filter_with_limits(self) -> list[AccessKey]:
        """Get keys that have data limits.

        :return: List of keys with limits
        """
        return [key for key in self.access_keys if key.has_data_limit]

    def filter_without_limits(self) -> list[AccessKey]:
        """Get keys without data limits.

        :return: List of keys without limits
        """
        return [key for key in self.access_keys if not key.has_data_limit]


class Server(BaseValidatedModel):
    """Server information model matching API schema.

    Represents Outline VPN server configuration and metadata.
    Based on OpenAPI schema: GET /server response
    """

    name: str
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
        """Check if server has global data limit.

        :return: True if global limit exists
        """
        return self.access_key_data_limit is not None

    @property
    def created_timestamp_seconds(self) -> float:
        """Get creation timestamp in seconds.

        :return: Timestamp in seconds
        """
        return self.created_timestamp_ms / _MS_IN_SEC


# ===== Metrics Models =====


class ServerMetrics(BaseValidatedModel):
    """Transfer metrics model matching API /metrics/transfer.

    Provides aggregated traffic statistics and analysis.
    Based on OpenAPI schema: GET /metrics/transfer response
    """

    bytes_transferred_by_user_id: BytesPerUserDict = Field(
        alias="bytesTransferredByUserId"
    )

    @property
    def total_bytes(self) -> int:
        """Calculate total bytes across all keys.

        :return: Total bytes transferred
        """
        return sum(self.bytes_transferred_by_user_id.values())

    @property
    def total_megabytes(self) -> float:
        """Get total in megabytes.

        :return: Total MB transferred
        """
        return self.total_bytes / _BYTES_IN_MB

    @property
    def total_gigabytes(self) -> float:
        """Get total in gigabytes.

        :return: Total GB transferred
        """
        return self.total_bytes / _BYTES_IN_GB

    @property
    def key_count(self) -> int:
        """Get number of keys with traffic.

        :return: Active key count
        """
        return len(self.bytes_transferred_by_user_id)

    def get_top_consumers(self, n: int = 10) -> list[tuple[str, int]]:
        """Get top N consumers by bytes.

        :param n: Number of top consumers
        :return: List of (key_id, bytes) tuples sorted by usage
        """
        if n < 1:
            return []

        sorted_items = sorted(
            self.bytes_transferred_by_user_id.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_items[:n]

    def get_usage_for_key(self, key_id: str) -> int:
        """Get bytes transferred for specific key.

        :param key_id: Access key ID
        :return: Bytes transferred or 0 if not found
        """
        return self.bytes_transferred_by_user_id.get(key_id, 0)


class MetricsStatusResponse(BaseValidatedModel):
    """Metrics status response matching API /metrics/enabled.

    Based on OpenAPI schema: GET /metrics/enabled response
    """

    metrics_enabled: bool = Field(alias="metricsEnabled")


# ===== Experimental Metrics Models =====


class TunnelTime(BaseValidatedModel, TimeConversionMixin):
    """Tunnel time metric in seconds.

    Based on OpenAPI schema: experimental metrics tunnelTime object
    """

    seconds: int = Field(ge=0)


class DataTransferred(BaseValidatedModel, ByteConversionMixin):
    """Data transfer metric in bytes.

    Based on OpenAPI schema: experimental metrics dataTransferred object
    """

    bytes: Bytes


class BandwidthDataValue(BaseValidatedModel):
    """Bandwidth data value.

    Based on OpenAPI schema: experimental metrics bandwidth data object
    """

    bytes: int


class BandwidthData(BaseValidatedModel):
    """Bandwidth measurement data.

    Based on OpenAPI schema: experimental metrics bandwidth current/peak object
    """

    data: BandwidthDataValue
    timestamp: TimestampSec | None = None


class BandwidthInfo(BaseValidatedModel):
    """Current and peak bandwidth information.

    Based on OpenAPI schema: experimental metrics bandwidth object
    """

    current: BandwidthData
    peak: BandwidthData


class LocationMetric(BaseValidatedModel):
    """Location-based usage metric.

    Based on OpenAPI schema: experimental metrics locations array item
    """

    location: str
    asn: int | None = None
    as_org: str | None = Field(None, alias="asOrg")
    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")


class PeakDeviceCount(BaseValidatedModel):
    """Peak device count with timestamp.

    Based on OpenAPI schema: experimental metrics connection peakDeviceCount object
    """

    data: int
    timestamp: TimestampSec


class ConnectionInfo(BaseValidatedModel):
    """Connection information and statistics.

    Based on OpenAPI schema: experimental metrics connection object
    """

    last_traffic_seen: TimestampSec = Field(alias="lastTrafficSeen")
    peak_device_count: PeakDeviceCount = Field(alias="peakDeviceCount")


class AccessKeyMetric(BaseValidatedModel):
    """Per-key experimental metrics.

    Based on OpenAPI schema: experimental metrics accessKeys array item
    """

    access_key_id: str = Field(alias="accessKeyId")
    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    connection: ConnectionInfo


class ServerExperimentalMetric(BaseValidatedModel):
    """Server-level experimental metrics.

    Based on OpenAPI schema: experimental metrics server object
    """

    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    bandwidth: BandwidthInfo
    locations: list[LocationMetric]


class ExperimentalMetrics(BaseValidatedModel):
    """Experimental metrics response matching API /experimental/server/metrics.

    Based on OpenAPI schema: GET /experimental/server/metrics response
    """

    server: ServerExperimentalMetric
    access_keys: list[AccessKeyMetric] = Field(alias="accessKeys")

    def get_key_metric(self, key_id: str) -> AccessKeyMetric | None:
        """Get metrics for specific key.

        :param key_id: Access key ID
        :return: Key metrics or None if not found
        """
        for metric in self.access_keys:
            if metric.access_key_id == key_id:
                return metric
        return None


# ===== Request Models =====


class AccessKeyCreateRequest(BaseValidatedModel):
    """Request model for creating access keys.

    All fields are optional for flexible key creation.
    Based on OpenAPI schema: POST /access-keys request body
    """

    name: str | None = None
    method: str | None = None
    password: str | None = None
    port: Port | None = None
    limit: DataLimit | None = None


class ServerNameRequest(BaseValidatedModel):
    """Request model for renaming server.

    Based on OpenAPI schema: PUT /name request body
    """

    name: str = Field(min_length=1, max_length=255)


class HostnameRequest(BaseValidatedModel):
    """Request model for setting hostname.

    Based on OpenAPI schema: PUT /server/hostname-for-access-keys request body
    """

    hostname: str = Field(min_length=1)


class PortRequest(BaseValidatedModel):
    """Request model for setting default port.

    Based on OpenAPI schema: PUT /server/port-for-new-access-keys request body
    """

    port: Port


class AccessKeyNameRequest(BaseValidatedModel):
    """Request model for renaming access key.

    Based on OpenAPI schema: PUT /access-keys/{id}/name request body
    """

    name: str = Field(min_length=1, max_length=255)


class DataLimitRequest(BaseValidatedModel):
    """Request model for setting data limit.

    Based on OpenAPI schema: PUT /access-keys/{id}/data-limit request body
    """

    limit: DataLimit


class MetricsEnabledRequest(BaseValidatedModel):
    """Request model for enabling/disabling metrics.

    Based on OpenAPI schema: PUT /metrics/enabled request body
    """

    metrics_enabled: bool = Field(alias="metricsEnabled")


# ===== Response Models =====


class ErrorResponse(BaseValidatedModel):
    """Error response model matching API error schema.

    Based on OpenAPI schema: error response format
    """

    code: str
    message: str

    def __str__(self) -> str:
        """Format error as string.

        :return: Formatted error message
        """
        return f"{self.code}: {self.message}"


# ===== Utility Models =====


class HealthCheckResult(BaseValidatedModel):
    """Health check result with diagnostic information."""

    healthy: bool
    timestamp: float
    checks: ChecksDict

    @property
    def failed_checks(self) -> list[str]:
        """Get failed checks.

        :return: List of failed check names
        """
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") != "healthy"
        ]

    @property
    def success_rate(self) -> float:
        """Calculate health check success rate.

        :return: Success rate (0.0 to 1.0)
        """
        if not self.checks:
            return 1.0

        total = len(self.checks)
        passed = total - len(self.failed_checks)
        return passed / total


class ServerSummary(BaseValidatedModel):
    """Server summary model with aggregated information."""

    server: dict[str, Any]
    access_keys_count: int
    healthy: bool
    transfer_metrics: BytesPerUserDict | None = None
    experimental_metrics: dict[str, Any] | None = None
    error: str | None = None

    @property
    def total_bytes_transferred(self) -> int:
        """Get total bytes if metrics available.

        :return: Total bytes or 0 if no metrics
        """
        if self.transfer_metrics:
            return sum(self.transfer_metrics.values())
        return 0

    @property
    def total_gigabytes_transferred(self) -> float:
        """Get total gigabytes if metrics available.

        :return: Total GB or 0.0 if no metrics
        """
        return self.total_bytes_transferred / _BYTES_IN_GB

    @property
    def has_errors(self) -> bool:
        """Check if summary contains errors.

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
