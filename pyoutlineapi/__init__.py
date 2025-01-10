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

import sys
from typing import TYPE_CHECKING

if sys.version_info < (3, 10):
    raise RuntimeError("PyOutlineAPI requires Python 3.10 or higher")

from .client import AsyncOutlineClient, OutlineError, APIError

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

__version__: str = "0.2.0"
__author__ = "Denis Rozhnovskiy"
__email__ = "pytelemonbot@mail.ru"
__license__ = "MIT"

PUBLIC_API = [
    "AsyncOutlineClient",
    "OutlineError",
    "APIError",
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
]

__all__ = PUBLIC_API

# Actual imports for runtime
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
