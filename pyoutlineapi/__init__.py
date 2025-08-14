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
from typing import Final


# Version check should be first
def _check_python_version() -> None:
    """Check if Python version is supported."""
    if sys.version_info < (3, 10):
        raise RuntimeError("PyOutlineAPI requires Python 3.10 or higher")


_check_python_version()

# Public API imports
from .client import AsyncOutlineClient, create_resilient_client
from .config import OutlineClientConfig, ConfigurationError, create_env_template
from .exceptions import (
    OutlineError,
    APIError,
    CircuitBreakerError,
    CircuitOpenError,
)

# Public model imports - only what users need
from .models import (
    # Core models that users will work with
    AccessKey,
    AccessKeyList,
    Server,
    DataLimit,
    ServerMetrics,
    ExperimentalMetrics,
    # Request models for creating/updating
    AccessKeyCreateRequest,
    DataLimitRequest,
    # Response models
    MetricsStatusResponse,
    # Utility models
    HealthCheckResult,
    ServerSummary,
    BatchOperationResult,
    # PerformanceMetrics removed - internal use only
)

# Public configuration classes
from .circuit_breaker import (
    CircuitConfig,
    CircuitState,
)

# Package metadata
try:
    __version__: str = metadata.version("pyoutlineapi")
except metadata.PackageNotFoundError:  # Fallback for development
    __version__ = "0.4.0-dev"

__author__: Final[str] = "Denis Rozhnovskiy"
__email__: Final[str] = "pytelemonbot@mail.ru"
__license__: Final[str] = "MIT"

# Clean public API - only what users should import
__all__: Final[list[str]] = [
    # Main client class
    "AsyncOutlineClient",
    "create_resilient_client",
    # Exceptions
    "OutlineError",
    "APIError",
    "CircuitBreakerError",
    "CircuitOpenError",
    # Core data models
    "AccessKey",
    "AccessKeyList",
    "Server",
    "DataLimit",
    "ServerMetrics",
    "ExperimentalMetrics",
    # Request/Response models
    "AccessKeyCreateRequest",
    "DataLimitRequest",
    "MetricsStatusResponse",
    # Utility models
    "HealthCheckResult",
    "ServerSummary",
    "BatchOperationResult",
    # Configuration
    "CircuitConfig",
    "CircuitState",
    "OutlineClientConfig",
    "ConfigurationError",
    # Factories and utilities
    "create_env_template",  # Template creation utility
    # Package info
    "__version__",
    "__author__",
    "__email__",
    "__license__",
]

# Enhanced internal class mapping
_internal_mapping = {
    "AsyncCircuitBreaker": "This is an internal class. Use CircuitConfig for configuration.",
    "BaseHTTPClient": "This is an internal class. Use AsyncOutlineClient instead.",
    "ResponseParser": "This is an internal utility. Response parsing is handled automatically.",
    "CircuitMetrics": "Use client.get_circuit_breaker_status() for circuit breaker metrics.",
    "PerformanceMetrics": "Use client.get_performance_metrics() to get performance data.",
    "ErrorResponse": "This is an internal model. Errors are raised as exceptions.",
    "OutlineHealthChecker": "Health checking is handled internally by the client.",
    "CommonValidators": "Validation is handled automatically by models.",
    "BatchProcessor": "Use batch operations on the client directly.",
    "HealthMonitor": "Health monitoring is handled internally by the client.",
    "PerformanceTracker": "Performance tracking is handled internally by the client.",
}


def __getattr__(name: str):
    """Handle missing attribute access with helpful error messages."""
    if name in _internal_mapping:
        raise AttributeError(
            f"{name} is not part of the public API. {_internal_mapping[name]}"
        )

    # For other internal classes
    if name.startswith("_") or any(
        name.endswith(suffix)
        for suffix in ["Mixin", "Parser", "Handler", "Tracker", "Monitor"]
    ):
        raise AttributeError(
            f"{name} is an internal implementation detail and not part of the public API. "
            f"Available public classes: {', '.join(__all__)}"
        )

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# Configuration template utility - exposed at top level for convenience
def create_config_template(file_path: str = ".env.example") -> None:
    """
    Create a comprehensive .env template file for Outline API configuration.

    This is a convenience wrapper around the config module's create_env_template function,
    exposed at the top level for easy access.

    Args:
        file_path: Path where to create the template file (default: ".env.example")

    Examples:
        Create default template:

        >>> import pyoutlineapi
        >>> pyoutlineapi.create_config_template()

        Create custom template:

        >>> pyoutlineapi.create_config_template(".env.production.template")

        CLI usage:
        $ python -c "import pyoutlineapi; pyoutlineapi.create_config_template()"
    """
    create_env_template(file_path)


# Add the template function to public API
__all__.append("create_config_template")


# Module-level convenience functions for quick setup
def quick_setup() -> None:
    """
    Quick setup helper that creates config template and shows usage examples.

    This function creates a .env.example file and prints helpful getting started info.

    Examples:

        >>> import pyoutlineapi
        >>> pyoutlineapi.quick_setup()
        ✓ Created .env.example template
        ✓ Edit the file with your server details
        ✓ Then use: AsyncOutlineClient.from_env()
    """
    try:
        create_config_template()
        print("🚀 PyOutlineAPI Quick Setup Complete!")
        print("")
        print("✓ Created .env.example with all configuration options")
        print("✓ Copy it to .env and fill in your server details:")
        print("  - OUTLINE_API_URL=https://your-server.com:port/secret")
        print("  - OUTLINE_CERT_SHA256=your-certificate-fingerprint")
        print("")
        print("📚 Usage examples:")
        print("  # Load from environment")
        print("  async with AsyncOutlineClient.from_env() as client:")
        print("      server = await client.get_server_info()")
        print("")
        print("  # Direct configuration")
        print("  async with create_client(api_url, cert_sha256) as client:")
        print("      keys = await client.get_access_keys()")
        print("")
        print("📖 Documentation: https://github.com/orenlab/pyoutlineapi")

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        print("💡 Try running with appropriate permissions or in a writable directory")


def get_version_info() -> dict[str, str]:
    """
    Get comprehensive version and package information.

    Returns:
        Dictionary with version, author, license, and repository information

    Examples:
        >>> import pyoutlineapi
        >>> info = pyoutlineapi.get_version_info()
        >>> print(f"PyOutlineAPI v{info['version']}")
    """
    return {
        "version": __version__,
        "author": __author__,
        "email": __email__,
        "license": __license__,
        "repository": "https://github.com/orenlab/pyoutlineapi",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_required": "3.10+",
    }


# Add convenience functions to public API
__all__.extend(["quick_setup", "get_version_info"])


# Auto-show helpful info when module is imported in interactive mode
def _show_interactive_help() -> None:
    """Show helpful information when imported in interactive Python."""
    try:
        # Check if we're in interactive mode
        if hasattr(sys, "ps1"):
            print(f"🐍 PyOutlineAPI v{__version__} - Outline VPN API Client")
            print("💡 Quick start: pyoutlineapi.quick_setup()")
            print("📚 Docs: help(pyoutlineapi.AsyncOutlineClient)")
    except:
        # Silently ignore any errors in interactive detection
        pass


# Show help in interactive mode
_show_interactive_help()
