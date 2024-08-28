"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutlineAPI project.

PyOutlineAPI is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.
"""

from typing import Optional, List, Dict

from pydantic import BaseModel, Field, SecretStr, constr, field_validator


class Server(BaseModel):
    """
    Model for server information.

    Attributes:
        name (str): The name of the server.
        serverId (str): The unique identifier for the server.
        metricsEnabled (bool): Indicates if metrics collection is enabled.
        createdTimestampMs (int): The timestamp when the server was created, must be non-negative.
        portForNewAccessKeys (int): The port used for new access keys, must be between 1 and 65535.
    """
    name: str
    serverId: str
    metricsEnabled: bool
    createdTimestampMs: int = Field(ge=0, description="Timestamp must be non-negative")
    portForNewAccessKeys: int = Field(ge=1, le=65535, description="Port must be between 1 and 65535")


class DataLimit(BaseModel):
    """
    Model for data limit information.

    Attributes:
        bytes (int): The data limit in bytes, must be non-negative.
    """
    bytes: int = Field(ge=0, description="Data limit in bytes must be non-negative")


class AccessKey(BaseModel):
    """
    Model for access key information.

    Attributes:
        id (str): The unique identifier for the access key.
        name (str): The name of the access key.
        password (SecretStr): The password for the access key, must not be empty.
        port (int): The port used by the access key, must be between 1 and 65535.
        method (str): The encryption method used by the access key.
        accessUrl (SecretStr): The URL used to access the server, must not be empty.
    """
    id: str
    name: str
    password: SecretStr = Field(..., min_length=1, description="Password must not be empty")
    port: int = Field(ge=1, le=65535, description="Port must be between 1 and 65535")
    method: str
    accessUrl: SecretStr = Field(..., min_length=1, description="Access URL must not be empty")


class ServerPort(BaseModel):
    """
    Model for server port information.

    Attributes:
        port (int): The port used by the server, must be between 1 and 65535.
    """
    port: int = Field(ge=1, le=65535, description="Port must be between 1 and 65535")


class AccessKeyCreateRequest(BaseModel):
    """
    Model for creating access key information.

    Attributes:
        name (Optional[str]): The name of the access key (optional).
        password (Optional[str]): The password for the access key (optional).
        port (Optional[int]): The port used by the access key, must be between 0 and 65535 (optional).
    """
    name: Optional[str]
    password: Optional[str]
    port: Optional[int] = Field(ge=0, le=65535, description="Port must be between 0 and 65535")


class AccessKeyList(BaseModel):
    """
    Model for access key list information.

    Attributes:
        accessKeys (List[AccessKey]): A list of access keys.
    """
    accessKeys: List[AccessKey]


class MetricsEnabled(BaseModel):
    """
    Model for metrics enabled information.

    Attributes:
        enabled (bool): Indicates if metrics collection is enabled.
    """
    enabled: bool


class Metrics(BaseModel):
    """
    Model for metrics information.

    Attributes:
        bytesTransferredByUserId (Dict[str, int]): A dictionary mapping user IDs to the number of bytes transferred.
        User IDs must be non-empty strings, and byte values must be non-negative.

    Methods:
        validate_bytes_transferred: Validates that all byte values in the dictionary are non-negative.
    """
    bytesTransferredByUserId: Dict[constr(min_length=1), int] = Field(
        description="User IDs must be non-empty strings and byte values must be non-negative")

    @field_validator("bytesTransferredByUserId")
    def validate_bytes_transferred(cls, value: Dict[str, int]) -> Dict[str, int]:
        """
        Validate that all byte values in the dictionary are non-negative.

        Args:
            value (Dict[str, int]): The dictionary to validate.

        Returns:
            Dict[str, int]: The validated dictionary.

        Raises:
            ValueError: If any byte value is negative.
        """
        for user_id, bytes_transferred in value.items():
            if bytes_transferred < 0:
                raise ValueError(f"Transferred bytes for user {user_id} must be non-negative")
        return value
