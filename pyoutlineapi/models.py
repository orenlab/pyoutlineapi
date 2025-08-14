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

from pydantic import Field, field_validator

from .common_types import (
    BaseValidatedModel,
    TimestampMixin,
    NamedEntityMixin,
    CommonValidators,
    Port,
    ServerId,
    AccessKeyId,
    Bytes,
    Timestamp,
)


class DataLimit(BaseValidatedModel):
    """Data transfer limit configuration."""

    bytes: Bytes = Field(description="Data limit in bytes")

    @classmethod
    @field_validator("bytes")
    def validate_bytes(cls, v: int) -> int:
        """Validate bytes using common validator."""
        return CommonValidators.validate_non_negative_bytes(v)


class AccessKey(BaseValidatedModel, TimestampMixin):
    """Access key details with enhanced validation."""

    id: AccessKeyId = Field(description="Access key identifier")
    name: str | None = Field(None, description="Access key name")
    password: str = Field(
        description="Access key password", repr=False
    )  # Hide from repr
    port: Port = Field(description="Port number")
    method: str = Field(description="Encryption method")
    access_url: str = Field(
        alias="accessUrl",
        description="Complete access URL",
        repr=False,  # Hide from repr for security
    )
    data_limit: DataLimit | None = Field(
        None, alias="dataLimit", description="Data limit for this key"
    )

    @classmethod
    @field_validator("name")
    def validate_name(cls, v: str | None) -> str | None:
        """Validate name if provided, handle empty strings from API."""
        return CommonValidators.validate_optional_name(v)


class AccessKeyList(BaseValidatedModel):
    """List of access keys."""

    access_keys: list[AccessKey] = Field(
        alias="accessKeys", description="List of access keys"
    )

    @property
    def count(self) -> int:
        """Get number of access keys."""
        return len(self.access_keys)

    def find_by_name(self, name: str) -> AccessKey | None:
        """Find access key by name."""
        for key in self.access_keys:
            if key.name == name:
                return key
        return None

    def find_by_id(self, key_id: str) -> AccessKey | None:
        """Find access key by ID."""
        for key in self.access_keys:
            if key.id == key_id:
                return key
        return None


class ServerMetrics(BaseValidatedModel):
    """Server metrics data for data transferred per access key."""

    bytes_transferred_by_user_id: dict[str, int] = Field(
        alias="bytesTransferredByUserId",
        description="Data transferred by each access key ID",
    )

    @classmethod
    @field_validator("bytes_transferred_by_user_id")
    def validate_bytes_transferred(cls, v: dict[str, int]) -> dict[str, int]:
        """Validate that all byte values are non-negative."""
        for key_id, bytes_count in v.items():
            if bytes_count < 0:
                raise ValueError(f"Bytes count for key {key_id} must be non-negative")
        return v

    @property
    def total_bytes_transferred(self) -> int:
        """Calculate total bytes transferred across all keys."""
        return sum(self.bytes_transferred_by_user_id.values())

    def get_usage_for_key(self, key_id: str) -> int:
        """Get usage for specific access key."""
        return self.bytes_transferred_by_user_id.get(key_id, 0)


class TunnelTime(BaseValidatedModel):
    """Tunnel time data structure."""

    seconds: int = Field(ge=0, description="Time in seconds")


class DataTransferred(BaseValidatedModel):
    """Data transfer information."""

    bytes: Bytes = Field(description="Bytes transferred")


class BandwidthData(BaseValidatedModel):
    """Bandwidth measurement data."""

    data: dict[str, int] = Field(description="Bandwidth data with bytes field")
    timestamp: Timestamp | None = Field(None, description="Unix timestamp")


class BandwidthInfo(BaseValidatedModel):
    """Current and peak bandwidth information."""

    current: BandwidthData = Field(description="Current bandwidth")
    peak: BandwidthData = Field(description="Peak bandwidth")


class LocationMetric(BaseValidatedModel):
    """Location metric model with improved validation."""

    location: str = Field(description="Location identifier")
    asn: int | None = Field(None, description="ASN number")
    as_org: str | None = Field(None, alias="asOrg", description="AS organization")
    tunnel_time: TunnelTime = Field(
        alias="tunnelTime", description="Tunnel time metrics"
    )
    data_transferred: DataTransferred = Field(
        alias="dataTransferred", description="Data transfer metrics"
    )

    @classmethod
    @field_validator("asn", mode="before")
    def validate_asn(cls, v) -> int | None:
        """Normalize ASN using common validator."""
        return CommonValidators.normalize_asn(v)

    @classmethod
    @field_validator("as_org", mode="before")
    def validate_as_org(cls, v) -> str | None:
        """Normalize AS organization using common validator."""
        return CommonValidators.normalize_empty_string(v)


class PeakDeviceCount(BaseValidatedModel):
    """Peak device count information."""

    data: int = Field(ge=0, description="Peak device count")
    timestamp: Timestamp = Field(description="Unix timestamp")


class ConnectionInfo(BaseValidatedModel):
    """Connection information for access keys."""

    last_traffic_seen: Timestamp = Field(
        alias="lastTrafficSeen", description="Last traffic timestamp"
    )
    peak_device_count: PeakDeviceCount = Field(
        alias="peakDeviceCount", description="Peak device count information"
    )


class AccessKeyMetric(BaseValidatedModel):
    """Access key metrics data."""

    access_key_id: AccessKeyId = Field(
        alias="accessKeyId", description="Access key identifier"
    )
    tunnel_time: TunnelTime = Field(
        alias="tunnelTime", description="Tunnel time metrics"
    )
    data_transferred: DataTransferred = Field(
        alias="dataTransferred", description="Data transfer metrics"
    )
    connection: ConnectionInfo = Field(description="Connection metrics")


class ServerExperimentalMetric(BaseValidatedModel):
    """Server-level experimental metrics."""

    tunnel_time: TunnelTime = Field(
        alias="tunnelTime", description="Server tunnel time"
    )
    data_transferred: DataTransferred = Field(
        alias="dataTransferred", description="Server data transfer"
    )
    bandwidth: BandwidthInfo = Field(description="Bandwidth information")
    locations: list[LocationMetric] = Field(description="Location-based metrics")


class ExperimentalMetrics(BaseValidatedModel):
    """Experimental metrics data structure."""

    server: ServerExperimentalMetric = Field(description="Server metrics")
    access_keys: list[AccessKeyMetric] = Field(
        alias="accessKeys", description="Access key metrics"
    )

    def get_metrics_for_key(self, key_id: str) -> AccessKeyMetric | None:
        """Get metrics for specific access key."""
        for metric in self.access_keys:
            if metric.access_key_id == key_id:
                return metric
        return None


class Server(BaseValidatedModel, NamedEntityMixin, TimestampMixin):
    """Server information with enhanced validation."""

    server_id: ServerId = Field(
        alias="serverId", description="Unique server identifier"
    )
    metrics_enabled: bool = Field(
        alias="metricsEnabled", description="Metrics sharing status"
    )
    created_timestamp_ms: Timestamp = Field(
        alias="createdTimestampMs", description="Creation timestamp in milliseconds"
    )
    version: str = Field(description="Server version")
    port_for_new_access_keys: Port = Field(
        alias="portForNewAccessKeys",
        description="Default port for new keys",
    )
    hostname_for_access_keys: str | None = Field(
        None, alias="hostnameForAccessKeys", description="Hostname for access keys"
    )
    access_key_data_limit: DataLimit | None = Field(
        None,
        alias="accessKeyDataLimit",
        description="Global data limit for access keys",
    )

    @property
    def uptime_hours(self) -> float:
        """Calculate server uptime in hours."""
        import time

        current_time_ms = time.time() * 1000
        return (current_time_ms - self.created_timestamp_ms) / (1000 * 60 * 60)


# Request Models
class AccessKeyCreateRequest(BaseValidatedModel):
    """Request parameters for creating an access key."""

    name: str | None = Field(None, description="Access key name")
    method: str | None = Field(None, description="Encryption method")
    password: str | None = Field(None, description="Access key password")
    port: Port | None = Field(None, description="Port number")
    limit: DataLimit | None = Field(None, description="Data limit for this key")

    @classmethod
    @field_validator("name")
    def validate_name(cls, v: str | None) -> str | None:
        """Validate name if provided, handle empty strings from API."""
        return CommonValidators.validate_optional_name(v)


class ServerNameRequest(BaseValidatedModel):
    """Request for renaming server."""

    name: str = Field(description="New server name")

    @classmethod
    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        """Validate name using common validator."""
        return CommonValidators.validate_name(v)


class HostnameRequest(BaseValidatedModel):
    """Request for changing hostname."""

    hostname: str = Field(description="New hostname or IP address")

    @classmethod
    @field_validator("hostname")
    def validate_hostname(cls, v: str) -> str:
        """Validate hostname format."""
        if not v or not v.strip():
            raise ValueError("Hostname cannot be empty")

        hostname = v.strip()

        # Basic hostname validation - can be IP or domain
        import re

        # Check for valid domain name pattern
        domain_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$"
        # IPv4 pattern
        ipv4_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        # IPv6 pattern (simplified)
        ipv6_pattern = r"^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$"

        # Check if hostname matches any valid pattern
        if not (
            re.match(domain_pattern, hostname)
            or re.match(ipv4_pattern, hostname)
            or re.match(ipv6_pattern, hostname)
        ):
            raise ValueError("Invalid hostname format")

        return hostname


class PortRequest(BaseValidatedModel):
    """Request for changing default port."""

    port: Port = Field(description="New default port")


class AccessKeyNameRequest(BaseValidatedModel):
    """Request for renaming access key."""

    name: str = Field(description="New access key name")

    @classmethod
    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        """Validate name using common validator."""
        return CommonValidators.validate_name(v)


class DataLimitRequest(BaseValidatedModel):
    """Request for setting data limit."""

    limit: DataLimit = Field(description="Data limit configuration")


class MetricsEnabledRequest(BaseValidatedModel):
    """Request for enabling/disabling metrics."""

    metrics_enabled: bool = Field(
        alias="metricsEnabled", description="Enable or disable metrics"
    )


# Response Models
class MetricsStatusResponse(BaseValidatedModel):
    """Response for /metrics/enabled endpoint."""

    metrics_enabled: bool = Field(
        alias="metricsEnabled", description="Current metrics status"
    )


class ErrorResponse(BaseValidatedModel):
    """Error response structure."""

    code: str = Field(description="Error code")
    message: str = Field(description="Error message")

    def __str__(self) -> str:
        """String representation of error."""
        return f"{self.code}: {self.message}"


# Utility Models
class HealthCheckResult(BaseValidatedModel, TimestampMixin):
    """Health check result model."""

    healthy: bool = Field(description="Overall health status")
    timestamp: float = Field(description="Timestamp of the check")
    checks: dict[str, dict[str, str | float | bool]] = Field(
        description="Individual check results"
    )
    detailed_metrics: dict[str, float | int | str] | None = Field(
        None, description="Detailed performance metrics if requested"
    )
    circuit_breaker_status: dict[str, bool | str | dict] | None = Field(
        None, description="Circuit breaker status if available"
    )

    @property
    def failed_checks(self) -> list[str]:
        """Get list of failed check names."""
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") != "healthy"
        ]

    @property
    def is_degraded(self) -> bool:
        """Check if service is in degraded state."""
        return any(
            result.get("status") == "degraded" for result in self.checks.values()
        )


class ServerSummary(BaseValidatedModel):
    """Server summary model for comprehensive overview."""

    server: dict[str, str | int | bool] = Field(description="Server information")
    access_keys_count: int = Field(description="Number of access keys")
    healthy: bool = Field(description="Server health status")
    transfer_metrics: dict[str, int] | None = Field(
        None, description="Transfer metrics if available"
    )
    experimental_metrics: dict[str, dict] | None = Field(
        None, description="Experimental metrics if available"
    )
    error: str | None = Field(None, description="Error message if unhealthy")

    @property
    def total_data_transferred(self) -> int:
        """Get total data transferred from metrics."""
        if not self.transfer_metrics:
            return 0

        bytes_by_user = self.transfer_metrics.get("bytesTransferredByUserId", {})
        return sum(bytes_by_user.values()) if isinstance(bytes_by_user, dict) else 0


class BatchOperationResult(BaseValidatedModel):
    """Result of batch operations."""

    total: int = Field(description="Total number of operations")
    successful: int = Field(description="Number of successful operations")
    failed: int = Field(description="Number of failed operations")
    results: list[dict[str, str | bool | dict]] = Field(
        description="Individual operation results"
    )
    errors: list[str] = Field(description="List of error messages")

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total == 0:
            return 1.0
        return self.successful / self.total

    @property
    def has_errors(self) -> bool:
        """Check if operation had any errors."""
        return self.failed > 0

    def get_successful_results(self) -> list[dict]:
        """Get only successful operation results."""
        return [result for result in self.results if result.get("success", False)]


class CircuitBreakerStatus(BaseValidatedModel):
    """Circuit breaker status model."""

    enabled: bool = Field(description="Whether circuit breaker is enabled")
    name: str | None = Field(None, description="Circuit breaker name")
    state: str | None = Field(None, description="Current state (CLOSED/OPEN/HALF_OPEN)")
    metrics: dict[str, int | float] | None = Field(
        None, description="Circuit breaker metrics"
    )
    config: dict[str, int | float] | None = Field(
        None, description="Circuit breaker configuration"
    )
    message: str | None = Field(None, description="Status message")

    @property
    def is_healthy(self) -> bool:
        """Check if circuit breaker is in healthy state."""
        return self.enabled and self.state in ("CLOSED", "HALF_OPEN")

    @property
    def failure_rate(self) -> float:
        """Get current failure rate."""
        if not self.metrics:
            return 0.0
        return self.metrics.get("failure_rate", 0.0)


class PerformanceMetrics(BaseValidatedModel):
    """Performance metrics model."""

    total_requests: int = Field(description="Total number of requests")
    successful_requests: int = Field(description="Number of successful requests")
    failed_requests: int = Field(description="Number of failed requests")
    circuit_breaker_trips: int = Field(description="Number of circuit breaker trips")
    avg_response_time: float = Field(description="Average response time in seconds")
    uptime: float = Field(description="Uptime in seconds")
    success_rate: float = Field(description="Success rate (0.0 to 1.0)")
    failure_rate: float = Field(description="Failure rate (0.0 to 1.0)")
    requests_per_minute: float = Field(description="Requests per minute rate")
    health_status: str = Field(description="Overall health status")
    circuit_breaker: dict[str, str | float | int] | None = Field(
        None, description="Circuit breaker specific metrics"
    )

    @property
    def is_healthy(self) -> bool:
        """Check if performance metrics indicate healthy state."""
        return self.health_status == "healthy"

    @property
    def uptime_hours(self) -> float:
        """Get uptime in hours."""
        return self.uptime / 3600

    @property
    def uptime_days(self) -> float:
        """Get uptime in days."""
        return self.uptime_hours / 24
