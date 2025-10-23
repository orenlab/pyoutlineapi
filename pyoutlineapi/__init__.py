"""PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi

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

from importlib import metadata
from typing import TYPE_CHECKING, Final, NoReturn

# Core imports
from .audit import (
    AuditLogger,
    DefaultAuditLogger,
    NoOpAuditLogger,
    get_default_audit_logger,
    set_default_audit_logger,
)
from .base_client import MetricsCollector, NoOpMetrics, correlation_id
from .circuit_breaker import CircuitConfig, CircuitMetrics, CircuitState
from .client import (
    AsyncOutlineClient,
    MultiServerManager,
    create_client,
    create_multi_server_manager,
)
from .common_types import (
    DEFAULT_SENSITIVE_KEYS,
    AuditDetails,
    ConfigOverrides,
    Constants,
    CredentialSanitizer,
    JsonPayload,
    MetricsTags,
    QueryParams,
    ResponseData,
    SecureIDGenerator,
    TimestampMs,
    TimestampSec,
    Validators,
    build_config_overrides,
    is_json_serializable,
    is_valid_bytes,
    is_valid_port,
    mask_sensitive_data,
    secure_compare,
)
from .config import (
    DevelopmentConfig,
    OutlineClientConfig,
    ProductionConfig,
    create_env_template,
    load_config,
)
from .exceptions import (
    APIError,
    CircuitOpenError,
    ConfigurationError,
    ConnectionError,
    OutlineError,
    TimeoutError,
    ValidationError,
    format_error_chain,
    get_retry_delay,
    get_safe_error_dict,
    is_retryable,
)
from .models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    AccessKeyMetric,
    AccessKeyNameRequest,
    BandwidthData,
    BandwidthDataValue,
    BandwidthInfo,
    ConnectionInfo,
    DataLimit,
    DataLimitRequest,
    DataTransferred,
    ErrorResponse,
    ExperimentalMetrics,
    HealthCheckResult,
    HostnameRequest,
    LocationMetric,
    MetricsEnabledRequest,
    MetricsStatusResponse,
    PeakDeviceCount,
    PortRequest,
    Server,
    ServerExperimentalMetric,
    ServerMetrics,
    ServerNameRequest,
    ServerSummary,
    TunnelTime,
)
from .response_parser import JsonDict, ResponseParser

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
    # Core client classes
    "AsyncOutlineClient",
    "MultiServerManager",
    # Audit
    "AuditDetails",
    "AuditLogger",
    "DefaultAuditLogger",
    "NoOpAuditLogger",
    # Circuit breaker
    "CircuitConfig",
    "CircuitMetrics",
    "CircuitOpenError",
    "CircuitState",
    # Configuration
    "ConfigOverrides",
    "ConfigurationError",
    "Constants",
    "DevelopmentConfig",
    "OutlineClientConfig",
    "ProductionConfig",
    # Common types and utilities
    "CredentialSanitizer",
    "DEFAULT_SENSITIVE_KEYS",
    "JsonDict",
    "JsonPayload",
    "MetricsTags",
    "QueryParams",
    "ResponseData",
    "SecureIDGenerator",
    "TimestampMs",
    "TimestampSec",
    "Validators",
    # Exceptions
    "APIError",
    "ConnectionError",
    "OutlineError",
    "TimeoutError",
    "ValidationError",
    # Metrics
    "MetricsCollector",
    "NoOpMetrics",
    # Models - Core
    "AccessKey",
    "AccessKeyCreateRequest",
    "AccessKeyList",
    "DataLimit",
    "DataLimitRequest",
    "Server",
    # Models - Request models
    "AccessKeyNameRequest",
    "HostnameRequest",
    "MetricsEnabledRequest",
    "PortRequest",
    "ServerNameRequest",
    # Models - Response models
    "ErrorResponse",
    "MetricsStatusResponse",
    "ServerMetrics",
    # Models - Experimental metrics
    "AccessKeyMetric",
    "BandwidthData",
    "BandwidthDataValue",
    "BandwidthInfo",
    "ConnectionInfo",
    "DataTransferred",
    "ExperimentalMetrics",
    "LocationMetric",
    "PeakDeviceCount",
    "ServerExperimentalMetric",
    "TunnelTime",
    # Models - Utility models
    "HealthCheckResult",
    "ServerSummary",
    # Response parser
    "ResponseParser",
    # Package metadata
    "__author__",
    "__email__",
    "__license__",
    "__version__",
    # Context variables
    "correlation_id",
    # Factory functions
    "create_client",
    "create_multi_server_manager",
    # Configuration utilities
    "build_config_overrides",
    "create_env_template",
    "load_config",
    # Audit utilities
    "get_default_audit_logger",
    "set_default_audit_logger",
    # Exception utilities
    "format_error_chain",
    "get_retry_delay",
    "get_safe_error_dict",
    "is_retryable",
    # Common utilities
    "get_version",
    "is_json_serializable",
    "is_valid_bytes",
    "is_valid_port",
    "mask_sensitive_data",
    "print_type_info",
    "quick_setup",
    "secure_compare",
]


# ===== Convenience Functions =====


def get_version() -> str:
    """Get package version string.

    :return: Package version
    """
    return __version__


def quick_setup() -> None:
    """Create configuration template file for quick setup.

    Creates `.env.example` file with all available configuration options.
    """
    create_env_template()
    print("✅ Created .env.example")
    print("📝 Edit the file with your server details")
    print("🚀 Then use: AsyncOutlineClient.from_env()")


def print_type_info() -> None:
    """Print information about available type aliases for advanced usage."""
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

Utility Classes:
    from pyoutlineapi import (
        CredentialSanitizer,
        SecureIDGenerator,
        ResponseParser,
    )

    # Sanitize sensitive data
    safe_url = CredentialSanitizer.sanitize(url)

    # Generate secure IDs
    secure_id = SecureIDGenerator.generate()

    # Parse API responses
    parsed = ResponseParser.parse(data, Model)

📖 Documentation: https://github.com/orenlab/pyoutlineapi
    """
    print(info)


# ===== Better Error Messages =====


def __getattr__(name: str) -> NoReturn:
    """Provide helpful error messages for common mistakes.

    :param name: Attribute name
    :raises AttributeError: If attribute not found
    """
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

if TYPE_CHECKING:
    import sys

    if hasattr(sys, "ps1"):
        # Show help in interactive mode
        print(f"🚀 PyOutlineAPI v{__version__}")
        print("💡 Quick start: pyoutlineapi.quick_setup()")
        print("🎯 Type hints: pyoutlineapi.print_type_info()")
        print("📚 Help: help(pyoutlineapi.AsyncOutlineClient)")
