"""PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

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

Advanced Usage - Type Hints:
    >>> from pyoutlineapi import (
    ...     AsyncOutlineClient,
    ...     AuditLogger,
    ...     AuditDetails,
    ...     MetricsCollector,
    ...     MetricsTags,
    ... )
    >>>
    >>> class CustomAuditLogger:
    ...     def log_action(
    ...         self,
    ...         action: str,
    ...         resource: str,
    ...         *,
    ...         user: str | None = None,
    ...         details: AuditDetails | None = None,
    ...         correlation_id: str | None = None,
    ...     ) -> None:
    ...         print(f"[AUDIT] {action} on {resource}")
    >>>
    >>> async with AsyncOutlineClient.create(
    ...     api_url="...",
    ...     cert_sha256="...",
    ...     audit_logger=CustomAuditLogger(),
    ... ) as client:
    ...     await client.create_access_key(name="test")
"""

from __future__ import annotations

import sys
from importlib import metadata
from typing import Final

# Version check
if sys.version_info < (3, 10):
    raise RuntimeError("PyOutlineAPI requires Python 3.10+")

# Core imports
from .audit import (
    AuditLogger,
    DefaultAuditLogger,
    NoOpAuditLogger,
    get_default_audit_logger,
    set_default_audit_logger,
)
from .base_client import MetricsCollector, correlation_id
from .circuit_breaker import CircuitConfig, CircuitState
from .client import AsyncOutlineClient, create_client

# Security utilities and validators
# Type aliases for advanced users
from .common_types import (
    DEFAULT_SENSITIVE_KEYS,
    AuditDetails,
    Constants,
    JsonPayload,
    MetricsTags,
    QueryParams,
    ResponseData,
    TimestampMs,
    TimestampSec,
    Validators,
    is_json_serializable,
    is_valid_bytes,
    is_valid_port,
    mask_sensitive_data,
    secure_compare,
)

# Configuration
from .config import (
    DevelopmentConfig,
    OutlineClientConfig,
    ProductionConfig,
    create_env_template,
    load_config,
)

# Exceptions
from .exceptions import (
    APIError,
    CircuitOpenError,
    ConfigurationError,
    ConnectionError,
    OutlineError,
    TimeoutError,
    ValidationError,
    get_retry_delay,
    get_safe_error_dict,
    is_retryable,
)

# Model imports
from .models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    DataLimit,
    DataLimitRequest,
    ExperimentalMetrics,
    HealthCheckResult,
    MetricsStatusResponse,
    Server,
    ServerMetrics,
    ServerSummary,
)

# Package metadata
try:
    __version__: str = metadata.version("pyoutlineapi")
except metadata.PackageNotFoundError:
    __version__ = "0.4.0-dev"

__author__: Final[str] = "Denis Rozhnovskiy"
__email__: Final[str] = "pytelemonbot@mail.ru"
__license__: Final[str] = "MIT"

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
    "get_retry_delay",
    "is_retryable",
    "get_safe_error_dict",
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
    # Security utilities
    "secure_compare",
    "mask_sensitive_data",
    "is_valid_port",
    "is_valid_bytes",
    "is_json_serializable",
    "DEFAULT_SENSITIVE_KEYS",
    # Constants and Validators
    "Constants",
    "Validators",
    # Enterprise features - UPDATED
    "AuditLogger",
    "DefaultAuditLogger",
    "NoOpAuditLogger",
    "get_default_audit_logger",
    "set_default_audit_logger",
    "MetricsCollector",
    "correlation_id",
    # Type aliases for advanced usage
    "TimestampMs",
    "TimestampSec",
    "JsonPayload",
    "ResponseData",
    "QueryParams",
    "AuditDetails",
    "MetricsTags",
    # Package info
    "__version__",
    "__author__",
    "__email__",
    "__license__",
]


# ===== Convenience Functions =====


def get_version() -> str:
    """Get package version string.

    Returns:
        str: Package version

    Example:
        >>> import pyoutlineapi
        >>> pyoutlineapi.get_version()
        '0.4.0'
    """
    return __version__


def quick_setup() -> None:
    """Create configuration template file for quick setup.

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

def print_type_info() -> None:
    """Print information about available type aliases for advanced usage.

    Example:
        >>> pyoutlineapi.print_type_info()
    """
    info = """
🎯 PyOutlineAPI Type Aliases for Advanced Usage
===============================================

For creating custom AuditLogger:
    from pyoutlineapi import AuditLogger, AuditDetails
    
    class MyAuditLogger:
        def log_action(
            self,
            action: str,
            resource: str,
            *,
            details: AuditDetails | None = None,
            ...
        ) -> None: ...
        
        async def alog_action(
            self,
            action: str,
            resource: str,
            *,
            details: AuditDetails | None = None,
            ...
        ) -> None: ...

For creating custom MetricsCollector:
    from pyoutlineapi import MetricsCollector, MetricsTags
    
    class MyMetrics:
        def increment(
            self,
            metric: str,
            *,
            tags: MetricsTags | None = None
        ) -> None: ...

Available Type Aliases:
    - TimestampMs, TimestampSec  # Unix timestamps
    - JsonPayload, ResponseData  # JSON data types
    - QueryParams                # URL query parameters
    - AuditDetails               # Audit log details
    - MetricsTags                # Metrics tags

Constants and Validators:
    from pyoutlineapi import Constants, Validators
    
    # Access constants
    Constants.RETRY_STATUS_CODES
    Constants.MIN_PORT, Constants.MAX_PORT
    
    # Use validators
    Validators.validate_port(8080)
    Validators.validate_key_id("my-key")

📖 Documentation: https://github.com/orenlab/pyoutlineapi
    """
    print(info)


# Add to public API
__all__.extend(["get_version", "print_type_info", "quick_setup"])


# ===== Better Error Messages =====


def __getattr__(name: str):
    """Provide helpful error messages for common mistakes."""
    mistakes = {
        "OutlineClient": "Use 'AsyncOutlineClient' instead",
        "OutlineSettings": "Use 'OutlineClientConfig' instead",
        "create_resilient_client": (
            "Use 'AsyncOutlineClient.create()' with 'enable_circuit_breaker=True'"
        ),
    }

    if name in mistakes:
        raise AttributeError(f"{name} not available. {mistakes[name]}")

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ===== Interactive Help =====

if hasattr(sys, "ps1"):
    # Show help in interactive mode
    print(f"🚀 PyOutlineAPI v{__version__}")
    print("💡 Quick start: pyoutlineapi.quick_setup()")
    print("🔒 Security info: pyoutlineapi.print_security_info()")
    print("🎯 Type hints: pyoutlineapi.print_type_info()")
    print("📚 Help: help(pyoutlineapi.AsyncOutlineClient)")
