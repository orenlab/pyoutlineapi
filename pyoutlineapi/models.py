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

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MetricsPeriod(str, Enum):
    """Time periods for metrics collection."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DataLimit(BaseModel):
    """Data transfer limit configuration."""

    bytes: int = Field(gt=0)

    @field_validator("bytes")
    def validate_bytes(cls, v: int) -> int:
        if v < 0:
            raise ValueError("bytes must be positive")
        return v


class AccessKey(BaseModel):
    """Access key details."""

    id: int
    name: Optional[str] = None
    password: str
    port: int = Field(gt=0, lt=65536)
    method: str
    access_url: str = Field(alias="accessUrl")
    data_limit: Optional[DataLimit] = Field(None, alias="dataLimit")


class AccessKeyList(BaseModel):
    """List of access keys."""

    access_keys: list[AccessKey] = Field(alias="accessKeys")


class ServerMetrics(BaseModel):
    """
    Server metrics data for data transferred per access key
    Per OpenAPI: /metrics/transfer endpoint
    """

    bytes_transferred_by_user_id: dict[str, int] = Field(
        alias="bytesTransferredByUserId"
    )


class TunnelData(BaseModel):
    seconds: int


class TransferData(BaseModel):
    bytes: int


class ServerMetric(BaseModel):
    location: str
    asn: Optional[int] = None
    as_org: Optional[str] = Field(None, alias="asOrg")
    tunnel_time: TunnelData = Field(alias="tunnelTime")
    data_transferred: TransferData = Field(alias="dataTransferred")


class AccessKeyMetric(BaseModel):
    access_key_id: int = Field(alias="accessKeyId")
    tunnel_time: TunnelData = Field(alias="tunnelTime")
    data_transferred: TransferData = Field(alias="dataTransferred")


class ExperimentalMetrics(BaseModel):
    """
    Experimental metrics data structure
    Per OpenAPI: /experimental/server/metrics endpoint
    """

    server: list[ServerMetric]
    access_keys: list[AccessKeyMetric] = Field(alias="accessKeys")


class Server(BaseModel):
    """
    Server information.
    Per OpenAPI: /server endpoint schema
    """

    name: str
    server_id: str = Field(alias="serverId")
    metrics_enabled: bool = Field(alias="metricsEnabled")
    created_timestamp_ms: int = Field(alias="createdTimestampMs")
    version: str
    port_for_new_access_keys: int = Field(alias="portForNewAccessKeys", gt=0, lt=65536)
    hostname_for_access_keys: Optional[str] = Field(None, alias="hostnameForAccessKeys")
    access_key_data_limit: Optional[DataLimit] = Field(None, alias="accessKeyDataLimit")


class AccessKeyCreateRequest(BaseModel):
    """
    Request parameters for creating an access key.
    Per OpenAPI: /access-keys POST request body
    """

    name: Optional[str] = None
    method: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = Field(None, gt=0, lt=65536)
    limit: Optional[DataLimit] = None


class MetricsStatusResponse(BaseModel):
    """Response for /metrics/enabled endpoint"""

    metrics_enabled: bool = Field(alias="metricsEnabled")


class ErrorResponse(BaseModel):
    """
    Error response structure
    Per OpenAPI: 404 and 400 responses
    """

    code: str
    message: str
