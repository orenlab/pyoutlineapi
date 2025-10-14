"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Quick Start:
    >>> from pyoutlineapi import AsyncOutlineClient
    >>>
    >>> # From environment variables
    >>> async with AsyncOutlineClient.from_env() as client:
    ...     server = await client.get_server_info()
    ...     print(f"Server: {server.name}")
    >>>
    >>> # With direct parameters
    >>> async with AsyncOutlineClient.create(
    ...     api_url="https://server.com:12345/secret",
    ...     cert_sha256="abc123...",
    ... ) as client:
    ...     keys = await client.get_access_keys()
"""

from __future__ import annotations

import sys
from importlib import metadata
from typing import Final

# Version check
if sys.version_info < (3, 10):
    raise RuntimeError("PyOutlineAPI requires Python 3.10+")

# Core imports
from .client import AsyncOutlineClient, create_client
from .config import (
    OutlineClientConfig,
    DevelopmentConfig,
    ProductionConfig,
    create_env_template,
    load_config,
)
from .exceptions import (
    OutlineError,
    APIError,
    CircuitOpenError,
    ConfigurationError,
    ValidationError,
    ConnectionError,
    TimeoutError,
)

# Model imports
from .models import (
    # Core
    AccessKey,
    AccessKeyList,
    Server,
    DataLimit,
    ServerMetrics,
    ExperimentalMetrics,
    MetricsStatusResponse,
    # Request models
    AccessKeyCreateRequest,
    DataLimitRequest,
    # Utility
    HealthCheckResult,
    ServerSummary,
)

# Circuit breaker (optional)
from .circuit_breaker import CircuitConfig, CircuitState

# Package metadata
try:
    __version__: str = metadata.version("pyoutlineapi")
except metadata.PackageNotFoundError:
    __version__ = "0.4.0-dev"

__author__: Final[str] = "Denis Rozhnovskiy"
__email__: Final[str] = "pytelemonbot@mail.ru"
__license__: Final[str] = "MIT"

# Note: Optional modules (health_monitoring, batch_operations, metrics_collector)
# are NOT imported here to keep imports fast. Import them explicitly:
#   from pyoutlineapi.health_monitoring import HealthMonitor
#   from pyoutlineapi.batch_operations import BatchOperations
#   from pyoutlineapi.metrics_collector import MetricsCollector

# Public API
__all__: Final[list[str]] = [
    # Main client
    "AsyncOutlineClient",
    "create_client",
    # Configuration
    "OutlineClientConfig",
    "DevelopmentConfig",
    "ProductionConfig",
    "load_config",
    "create_env_template",
    # Exceptions
    "OutlineError",
    "APIError",
    "CircuitOpenError",
    "ConfigurationError",
    "ValidationError",
    "ConnectionError",
    "TimeoutError",
    # Core models
    "AccessKey",
    "AccessKeyList",
    "Server",
    "DataLimit",
    "ServerMetrics",
    "ExperimentalMetrics",
    "MetricsStatusResponse",
    # Request models
    "AccessKeyCreateRequest",
    "DataLimitRequest",
    # Utility models
    "HealthCheckResult",
    "ServerSummary",
    # Circuit breaker
    "CircuitConfig",
    "CircuitState",
    # Package info
    "__version__",
    "__author__",
    "__email__",
    "__license__",
]


# ===== Convenience Functions =====


def get_version() -> str:
    """
    Get package version string.

    Returns:
        str: Package version

    Example:
        >>> import pyoutlineapi
        >>> pyoutlineapi.get_version()
        '0.4.0'
    """
    return __version__


def quick_setup() -> None:
    """
    Create configuration template file for quick setup.

    Creates `.env.example` file with all available configuration options.

    Example:
        >>> import pyoutlineapi
        >>> pyoutlineapi.quick_setup()
        ✅ Created .env.example
        📝 Edit the file with your server details
        🚀 Then use: AsyncOutlineClient.from_env()
    """
    create_env_template()
    print("✅ Created .env.example")
    print("📝 Edit the file with your server details")
    print("🚀 Then use: AsyncOutlineClient.from_env()")


# Add to public API
__all__.extend(["get_version", "quick_setup"])


# ===== Better Error Messages =====


def __getattr__(name: str):
    """Provide helpful error messages for common mistakes."""

    # Common mistakes
    mistakes = {
        "OutlineClient": "Use 'AsyncOutlineClient' instead",
        "OutlineSettings": "Use 'OutlineClientConfig' instead",
        "create_resilient_client": "Use 'AsyncOutlineClient.create()' with 'enable_circuit_breaker=True'",
    }

    if name in mistakes:
        raise AttributeError(f"{name} not available. {mistakes[name]}")

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ===== Interactive Help =====

if hasattr(sys, "ps1"):
    # Show help in interactive mode
    print(f"🚀 PyOutlineAPI v{__version__}")
    print("💡 Quick start: pyoutlineapi.quick_setup()")
    print("📚 Help: help(pyoutlineapi.AsyncOutlineClient)")
