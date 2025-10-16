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

from typing import Any

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

# ===== Core Models =====


class DataLimit(BaseValidatedModel):
    """Data transfer limit in bytes.

    IMPROVEMENTS:
    - Helper methods for common conversions
    """

    bytes: Bytes

    @property
    def megabytes(self) -> float:
        """Get limit in megabytes."""
        return self.bytes / (1024**2)

    @property
    def gigabytes(self) -> float:
        """Get limit in gigabytes."""
        return self.bytes / (1024**3)

    @classmethod
    def from_megabytes(cls, mb: float) -> DataLimit:
        """Create DataLimit from megabytes."""
        return cls(bytes=int(mb * 1024**2))

    @classmethod
    def from_gigabytes(cls, gb: float) -> DataLimit:
        """Create DataLimit from gigabytes."""
        return cls(bytes=int(gb * 1024**3))


class AccessKey(BaseValidatedModel):
    """Access key model (matches API schema).

    IMPROVEMENTS:
    - Enhanced validation
    - Helper methods
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
        """Handle empty names from API."""
        return Validators.validate_name(v)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate key ID."""
        return Validators.validate_key_id(v)

    @property
    def has_data_limit(self) -> bool:
        """Check if key has data limit set."""
        return self.data_limit is not None

    @property
    def display_name(self) -> str:
        """Get display name (name or id if no name)."""
        return self.name if self.name else f"Key-{self.id}"


class AccessKeyList(BaseValidatedModel):
    """List of access keys (matches API schema).

    IMPROVEMENTS:
    - Helper methods for filtering
    """

    access_keys: list[AccessKey] = Field(alias="accessKeys")

    @property
    def count(self) -> int:
        """Get number of access keys."""
        return len(self.access_keys)

    def get_by_id(self, key_id: str) -> AccessKey | None:
        """Get key by ID."""
        for key in self.access_keys:
            if key.id == key_id:
                return key
        return None

    def get_by_name(self, name: str) -> list[AccessKey]:
        """Get keys by name (may return multiple)."""
        return [key for key in self.access_keys if key.name == name]

    def filter_with_limits(self) -> list[AccessKey]:
        """Get keys that have data limits."""
        return [key for key in self.access_keys if key.has_data_limit]


class Server(BaseValidatedModel):
    """Server information model (matches API schema).

    IMPROVEMENTS:
    - Helper methods
    - Better field descriptions
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
        """Validate server name."""
        validated = Validators.validate_name(v)
        if validated is None:
            raise ValueError("Server name cannot be empty")
        return validated

    @property
    def has_global_limit(self) -> bool:
        """Check if server has global data limit."""
        return self.access_key_data_limit is not None

    @property
    def created_timestamp_seconds(self) -> float:
        """Get creation timestamp in seconds."""
        return self.created_timestamp_ms / 1000.0


# ===== Metrics Models =====


class ServerMetrics(BaseValidatedModel):
    """Transfer metrics model (matches API /metrics/transfer).

    IMPROVEMENTS:
    - Enhanced helper methods
    """

    bytes_transferred_by_user_id: BytesPerUserDict = Field(
        alias="bytesTransferredByUserId"
    )

    @property
    def total_bytes(self) -> int:
        """Calculate total bytes across all keys."""
        return sum(self.bytes_transferred_by_user_id.values())

    @property
    def total_gigabytes(self) -> float:
        """Get total in gigabytes."""
        return self.total_bytes / (1024**3)

    @property
    def key_count(self) -> int:
        """Get number of keys with traffic."""
        return len(self.bytes_transferred_by_user_id)

    def get_top_consumers(self, n: int = 10) -> list[tuple[str, int]]:
        """Get top N consumers by bytes."""
        sorted_items = sorted(
            self.bytes_transferred_by_user_id.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_items[:n]


class MetricsStatusResponse(BaseValidatedModel):
    """Metrics status response (matches API /metrics/enabled)."""

    metrics_enabled: bool = Field(alias="metricsEnabled")


# ===== Experimental Metrics Models =====


class TunnelTime(BaseValidatedModel):
    """Tunnel time metric in seconds."""

    seconds: int = Field(ge=0)


class DataTransferred(BaseValidatedModel):
    """Data transfer metric in bytes."""

    bytes: Bytes

    @property
    def gigabytes(self) -> float:
        """Get in gigabytes."""
        return self.bytes / (1024**3)


class BandwidthDataValue(BaseValidatedModel):
    """Bandwidth data value (nested in BandwidthData)."""

    bytes: int


class BandwidthData(BaseValidatedModel):
    """Bandwidth measurement data.

    API Example:
    {"data": {"bytes": 10}, "timestamp": 1739284734}
    """

    data: BandwidthDataValue
    timestamp: TimestampSec | None = None


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


class PeakDeviceCount(BaseValidatedModel):
    """Peak device count with timestamp.

    API Schema:
    peakDeviceCount:
      type: object
      properties:
        data: type: integer
        timestamp: type: integer (in seconds)
    """

    data: int
    timestamp: TimestampSec


class ConnectionInfo(BaseValidatedModel):
    """Connection information and statistics."""

    last_traffic_seen: TimestampSec = Field(alias="lastTrafficSeen")
    peak_device_count: PeakDeviceCount = Field(alias="peakDeviceCount")


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
    """Experimental metrics response (matches API /experimental/server/metrics)."""

    server: ServerExperimentalMetric
    access_keys: list[AccessKeyMetric] = Field(alias="accessKeys")

    def get_key_metric(self, key_id: str) -> AccessKeyMetric | None:
        """Get metrics for specific key."""
        for metric in self.access_keys:
            if metric.access_key_id == key_id:
                return metric
        return None


# ===== Request Models =====


class AccessKeyCreateRequest(BaseValidatedModel):
    """Request model for creating access keys."""

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
    """Error response model (matches API error schema)."""

    code: str
    message: str

    def __str__(self) -> str:
        """Format error as string."""
        return f"{self.code}: {self.message}"


# ===== Utility Models =====


class HealthCheckResult(BaseValidatedModel):
    """Health check result (custom utility model)."""

    healthy: bool
    timestamp: float
    checks: ChecksDict

    @property
    def failed_checks(self) -> list[str]:
        """Get failed checks."""
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") != "healthy"
        ]


class ServerSummary(BaseValidatedModel):
    """Server summary model (custom utility model)."""

    server: dict[str, Any]
    access_keys_count: int
    healthy: bool
    transfer_metrics: BytesPerUserDict | None = None
    experimental_metrics: dict[str, Any] | None = None
    error: str | None = None

    @property
    def total_bytes_transferred(self) -> int:
        """Get total bytes if metrics available."""
        if self.transfer_metrics:
            return sum(self.transfer_metrics.values())
        return 0


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
