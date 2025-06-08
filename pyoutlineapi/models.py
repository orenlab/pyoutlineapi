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

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DataLimit(BaseModel):
    """Data transfer limit configuration."""

    bytes: int = Field(ge=0, description="Data limit in bytes")

    @classmethod
    @field_validator("bytes")
    def validate_bytes(cls, v: int) -> int:
        if v < 0:
            raise ValueError("bytes must be non-negative")
        return v


class AccessKey(BaseModel):
    """Access key details."""

    id: str = Field(description="Access key identifier")
    name: Optional[str] = Field(None, description="Access key name")
    password: str = Field(description="Access key password")
    port: int = Field(gt=0, lt=65536, description="Port number")
    method: str = Field(description="Encryption method")
    access_url: str = Field(alias="accessUrl", description="Complete access URL")
    data_limit: Optional[DataLimit] = Field(
        None, alias="dataLimit", description="Data limit for this key"
    )


class AccessKeyList(BaseModel):
    """List of access keys."""

    access_keys: list[AccessKey] = Field(alias="accessKeys")


class ServerMetrics(BaseModel):
    """
    Server metrics data for data transferred per access key.
    Per OpenAPI: /metrics/transfer endpoint
    """

    bytes_transferred_by_user_id: dict[str, int] = Field(
        alias="bytesTransferredByUserId",
        description="Data transferred by each access key ID",
    )


class TunnelTime(BaseModel):
    """Tunnel time data structure."""

    seconds: int = Field(description="Time in seconds")


class DataTransferred(BaseModel):
    """Data transfer information."""

    bytes: int = Field(description="Bytes transferred")


class BandwidthData(BaseModel):
    """Bandwidth measurement data."""

    data: dict[str, int] = Field(description="Bandwidth data with bytes field")
    timestamp: Optional[int] = Field(None, description="Unix timestamp")


class BandwidthInfo(BaseModel):
    """Current and peak bandwidth information."""

    current: BandwidthData = Field(description="Current bandwidth")
    peak: BandwidthData = Field(description="Peak bandwidth")


class LocationMetric(BaseModel):
    """Location metric model."""
    location: str = Field(..., description="Location identifier")
    asn: Optional[int] = Field(None, description="ASN number")
    as_org: Optional[str] = Field(None, alias="asOrg", description="AS organization")
    tunnel_time: "TunnelTime" = Field(..., alias="tunnelTime")
    data_transferred: "DataTransferred" = Field(..., alias="dataTransferred")

    @classmethod
    @field_validator('asn', mode='before')
    def validate_asn(cls, v):
        """Convert 0 to None for ASN."""
        if v == 0:
            return None
        return v

    @classmethod
    @field_validator('as_org', mode='before')
    def validate_as_org(cls, v):
        """Convert empty string to None for AS organization."""
        if v == "" or v == 0:
            return None
        return v


class PeakDeviceCount(BaseModel):
    """Peak device count information."""

    data: int = Field(description="Peak device count")
    timestamp: int = Field(description="Unix timestamp")


class ConnectionInfo(BaseModel):
    """Connection information for access keys."""

    last_traffic_seen: int = Field(
        alias="lastTrafficSeen", description="Last traffic timestamp"
    )
    peak_device_count: PeakDeviceCount = Field(alias="peakDeviceCount")


class AccessKeyMetric(BaseModel):
    """Access key metrics data."""

    access_key_id: int = Field(alias="accessKeyId")
    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    connection: ConnectionInfo = Field(description="Connection metrics")


class ServerExperimentalMetric(BaseModel):
    """Server-level experimental metrics."""

    tunnel_time: TunnelTime = Field(alias="tunnelTime")
    data_transferred: DataTransferred = Field(alias="dataTransferred")
    bandwidth: BandwidthInfo = Field(description="Bandwidth information")
    locations: list[LocationMetric] = Field(description="Location-based metrics")


class ExperimentalMetrics(BaseModel):
    """
    Experimental metrics data structure.
    Per OpenAPI: /experimental/server/metrics endpoint
    """

    server: ServerExperimentalMetric = Field(description="Server metrics")
    access_keys: list[AccessKeyMetric] = Field(
        alias="accessKeys", description="Access key metrics"
    )


class Server(BaseModel):
    """
    Server information.
    Per OpenAPI: /server endpoint schema
    """

    name: str = Field(description="Server name")
    server_id: str = Field(alias="serverId", description="Unique server identifier")
    metrics_enabled: bool = Field(
        alias="metricsEnabled", description="Metrics sharing status"
    )
    created_timestamp_ms: int = Field(
        alias="createdTimestampMs", description="Creation timestamp in milliseconds"
    )
    version: str = Field(description="Server version")
    port_for_new_access_keys: int = Field(
        alias="portForNewAccessKeys",
        gt=0,
        lt=65536,
        description="Default port for new keys",
    )
    hostname_for_access_keys: Optional[str] = Field(
        None, alias="hostnameForAccessKeys", description="Hostname for access keys"
    )
    access_key_data_limit: Optional[DataLimit] = Field(
        None,
        alias="accessKeyDataLimit",
        description="Global data limit for access keys",
    )


class AccessKeyCreateRequest(BaseModel):
    """
    Request parameters for creating an access key.
    Per OpenAPI: /access-keys POST request body
    """

    name: Optional[str] = Field(None, description="Access key name")
    method: Optional[str] = Field(None, description="Encryption method")
    password: Optional[str] = Field(None, description="Access key password")
    port: Optional[int] = Field(None, gt=0, lt=65536, description="Port number")
    limit: Optional[DataLimit] = Field(None, description="Data limit for this key")


class ServerNameRequest(BaseModel):
    """Request for renaming server."""

    name: str = Field(description="New server name")


class HostnameRequest(BaseModel):
    """Request for changing hostname."""

    hostname: str = Field(description="New hostname or IP address")


class PortRequest(BaseModel):
    """Request for changing default port."""

    port: int = Field(gt=0, lt=65536, description="New default port")


class AccessKeyNameRequest(BaseModel):
    """Request for renaming access key."""

    name: str = Field(description="New access key name")


class DataLimitRequest(BaseModel):
    """Request for setting data limit."""

    limit: DataLimit = Field(description="Data limit configuration")


class MetricsEnabledRequest(BaseModel):
    """Request for enabling/disabling metrics."""

    metrics_enabled: bool = Field(
        alias="metricsEnabled", description="Enable or disable metrics"
    )


class MetricsStatusResponse(BaseModel):
    """Response for /metrics/enabled endpoint."""

    metrics_enabled: bool = Field(
        alias="metricsEnabled", description="Current metrics status"
    )


class ErrorResponse(BaseModel):
    """
    Error response structure.
    Per OpenAPI: 404 and 400 responses
    """

    code: str = Field(description="Error code")
    message: str = Field(description="Error message")
