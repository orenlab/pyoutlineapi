"""PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

from __future__ import annotations

from typing import Any, ClassVar

from .common_types import Constants


class OutlineError(Exception):
    """Base exception for all PyOutlineAPI errors.

    Features:
    - Rich error context
    - Retry guidance
    - Safe serialization (no secrets)
    """

    is_retryable: ClassVar[bool] = False
    default_retry_delay: ClassVar[float] = 1.0

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        safe_details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize exception.

        Args:
            message: Error message
            details: Internal details (may contain sensitive data)
            safe_details: Safe details for logging/display
        """
        super().__init__(message)
        self._details = details or {}
        self._safe_details = safe_details or {}

    @property
    def details(self) -> dict[str, Any]:
        """Get internal details (use with caution)."""
        return self._details

    @property
    def safe_details(self) -> dict[str, Any]:
        """Get safe details (for logging/display)."""
        return self._safe_details

    def __str__(self) -> str:
        """Safe string representation using safe_details."""
        if not self._safe_details:
            return super().__str__()
        details_str = ", ".join(f"{k}={v}" for k, v in self._safe_details.items())
        return f"{super().__str__()} ({details_str})"

    def __repr__(self) -> str:
        """Safe repr without sensitive data."""
        class_name = self.__class__.__name__
        message = super().__str__()
        return f"{class_name}({message!r})"


class APIError(OutlineError):
    """API request failure.

    Automatically determines retry eligibility based on HTTP status.
    Uses Constants.RETRY_STATUS_CODES for consistency.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        # Sanitize endpoint for safe display
        from .common_types import Validators

        safe_endpoint = (
            Validators.sanitize_endpoint_for_logging(endpoint) if endpoint else None
        )

        safe_details = {}
        if status_code is not None:
            safe_details["status_code"] = status_code
        if safe_endpoint is not None:
            safe_details["endpoint"] = safe_endpoint

        details = {"status_code": status_code, "endpoint": endpoint}

        super().__init__(message, details=details, safe_details=safe_details)
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_data = response_data

        # Use centralized retry codes from Constants
        self.is_retryable = (
            status_code in Constants.RETRY_STATUS_CODES if status_code else False
        )

    @property
    def is_client_error(self) -> bool:
        """Check if this is a client error (4xx)."""
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        """Check if this is a server error (5xx)."""
        return self.status_code is not None and 500 <= self.status_code < 600


class CircuitOpenError(OutlineError):
    """Circuit breaker is open."""

    is_retryable: ClassVar[bool] = True

    def __init__(self, message: str, *, retry_after: float = 60.0) -> None:
        safe_details = {"retry_after": retry_after}
        super().__init__(message, safe_details=safe_details)
        self.retry_after = retry_after
        self.default_retry_delay = retry_after


class ConfigurationError(OutlineError):
    """Configuration validation error."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        security_issue: bool = False,
    ) -> None:
        safe_details: dict[str, Any] = {}
        if field:
            safe_details["field"] = field
        if security_issue:
            safe_details["security_issue"] = True

        super().__init__(message, safe_details=safe_details)
        self.field = field
        self.security_issue = security_issue


class ValidationError(OutlineError):
    """Data validation error."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        model: str | None = None,
    ) -> None:
        safe_details: dict[str, Any] = {}
        if field:
            safe_details["field"] = field
        if model:
            safe_details["model"] = model

        super().__init__(message, safe_details=safe_details)
        self.field = field
        self.model = model


class ConnectionError(OutlineError):
    """Connection failure."""

    is_retryable: ClassVar[bool] = True
    default_retry_delay: ClassVar[float] = 2.0

    def __init__(
        self,
        message: str,
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        safe_details: dict[str, Any] = {}
        if host:
            safe_details["host"] = host
        if port:
            safe_details["port"] = port

        super().__init__(message, safe_details=safe_details)
        self.host = host
        self.port = port


class TimeoutError(OutlineError):
    """Operation timeout."""

    is_retryable: ClassVar[bool] = True
    default_retry_delay: ClassVar[float] = 2.0

    def __init__(
        self,
        message: str,
        *,
        timeout: float | None = None,
        operation: str | None = None,
    ) -> None:
        safe_details: dict[str, Any] = {}
        if timeout is not None:
            safe_details["timeout"] = timeout
        if operation:
            safe_details["operation"] = operation

        super().__init__(message, safe_details=safe_details)
        self.timeout = timeout
        self.operation = operation


# ===== Utility Functions =====


def get_retry_delay(error: Exception) -> float | None:
    """Get suggested retry delay for an error."""
    if not isinstance(error, OutlineError):
        return None
    if not error.is_retryable:
        return None
    return getattr(error, "default_retry_delay", 1.0)


def is_retryable(error: Exception) -> bool:
    """Check if error is retryable."""
    if isinstance(error, OutlineError):
        return error.is_retryable
    return False


def get_safe_error_dict(error: Exception) -> dict[str, Any]:
    """Get safe error dictionary for logging/monitoring.

    Returns only safe information, no sensitive data.
    """
    result: dict[str, Any] = {
        "type": type(error).__name__,
        "message": str(error),
    }

    if isinstance(error, OutlineError):
        result["retryable"] = error.is_retryable
        result["retry_delay"] = error.default_retry_delay
        result["safe_details"] = error.safe_details

    return result


__all__ = [
    "APIError",
    "CircuitOpenError",
    "ConfigurationError",
    "ConnectionError",
    "OutlineError",
    "TimeoutError",
    "ValidationError",
    "get_retry_delay",
    "get_safe_error_dict",
    "is_retryable",
]
