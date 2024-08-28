"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutline project.

PyOutline is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""

from typing import Optional, List, Dict

from pydantic import BaseModel, Field, SecretStr, constr, field_validator


class Server(BaseModel):
    name: str
    serverId: str
    metricsEnabled: bool
    createdTimestampMs: int = Field(ge=0, description="Timestamp must be non-negative")
    portForNewAccessKeys: int = Field(ge=1, le=65535, description="Port must be between 1 and 65535")


class DataLimit(BaseModel):
    bytes: int = Field(ge=0, description="Data limit in bytes must be non-negative")


class AccessKey(BaseModel):
    id: str
    name: Optional[str]
    password: SecretStr = Field(..., min_length=1, description="Password must not be empty")
    port: int = Field(ge=1, le=65535, description="Port must be between 1 and 65535")
    method: str
    accessUrl: SecretStr = Field(..., min_length=1, description="Access URL must not be empty")


class AccessKeyList(BaseModel):
    accessKeys: List[AccessKey]


class ServerPort(BaseModel):
    port: int = Field(ge=1, le=65535, description="Port must be between 1 and 65535")


class MetricsEnabled(BaseModel):
    enabled: bool


class Metrics(BaseModel):
    bytesTransferredByUserId: Dict[constr(min_length=1), int] = Field(
        description="User IDs must be non-empty strings and byte values must be non-negative")

    @field_validator("bytesTransferredByUserId")
    def validate_bytes_transferred(cls, value: Dict[str, int]) -> Dict[str, int]:
        for user_id, bytes_transferred in value.items():
            if bytes_transferred < 0:
                raise ValueError(f"Transferred bytes for user {user_id} must be non-negative")
        return value
