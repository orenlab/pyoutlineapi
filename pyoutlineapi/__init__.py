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

# Version check
if sys.version_info < (3, 10):
    raise RuntimeError("PyOutlineAPI requires Python 3.10 or higher")

# Core client imports
from .client import AsyncOutlineClient
from .exceptions import APIError, OutlineError
from .rate_limiter import RateLimiter, rate_limit

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
        DataLimit,
        ErrorResponse,
        ExperimentalMetrics,
        MetricsPeriod,
        MetricsStatusResponse,
        Server,
        ServerMetrics,
    )

# Runtime imports
from .models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    DataLimit,
    ErrorResponse,
    ExperimentalMetrics,
    MetricsPeriod,
    MetricsStatusResponse,
    Server,
    ServerMetrics,
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
    "DataLimit",
    "ErrorResponse",
    "ExperimentalMetrics",
    "MetricsPeriod",
    "MetricsStatusResponse",
    "Server",
    "ServerMetrics",
    # Rate limiter
    "RateLimiter",
    "rate_limit",
]
