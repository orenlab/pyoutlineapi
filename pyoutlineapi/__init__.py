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

import sys
from importlib import metadata
from typing import Final, TYPE_CHECKING


def check_python_version():
    if sys.version_info < (3, 10):
        raise RuntimeError("PyOutlineAPI requires Python 3.10 or higher")


check_python_version()

# Core client imports
from .client import AsyncOutlineClient
from .exceptions import APIError, OutlineError

# Package metadata
try:
    __version__: str = metadata.version("pyoutlineapi")
except metadata.PackageNotFoundError:  # Fallback for development
    __version__ = "0.3.0-dev"

__author__: Final[str] = "Denis Rozhnovskiy"
__email__: Final[str] = "pytelemonbot@mail.ru"
__license__: Final[str] = "MIT"

# Type checking imports
if TYPE_CHECKING:
    from .models import (
        AccessKey,
        AccessKeyCreateRequest,
        AccessKeyList,
        AccessKeyNameRequest,
        DataLimit,
        DataLimitRequest,
        ErrorResponse,
        ExperimentalMetrics,
        HostnameRequest,
        MetricsEnabledRequest,
        MetricsStatusResponse,
        PortRequest,
        Server,
        ServerMetrics,
        ServerNameRequest
    )

# Runtime imports
from .models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    AccessKeyNameRequest,
    DataLimit,
    DataLimitRequest,
    ErrorResponse,
    ExperimentalMetrics,
    HostnameRequest,
    MetricsEnabledRequest,
    MetricsStatusResponse,
    PortRequest,
    Server,
    ServerMetrics,
    ServerNameRequest,
)

__all__: Final[list[str]] = [
    # Client
    "AsyncOutlineClient",
    "OutlineError",
    "APIError",
    # Models
    "AccessKey",
    "AccessKeyCreateRequest",
    "AccessKeyList",
    "AccessKeyNameRequest",
    "DataLimit",
    "DataLimitRequest",
    "ErrorResponse",
    "ExperimentalMetrics",
    "HostnameRequest",
    "MetricsEnabledRequest",
    "MetricsStatusResponse",
    "PortRequest",
    "Server",
    "ServerMetrics",
    "ServerNameRequest",
]
