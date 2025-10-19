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

from typing import Any, ClassVar, Final

# Maximum length for error messages to prevent DoS
_MAX_MESSAGE_LENGTH: Final[int] = 1024


class OutlineError(Exception):
    """Base exception for all PyOutlineAPI errors.

    Provides rich error context, retry guidance, and safe serialization.

    Security features:
    - Separate internal and safe details
    - Message length limits
    - No sensitive data in string representations
    - Immutable details after creation
    """

    __slots__ = ("_details", "_message", "_safe_details")

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

        :param message: Error message
        :param details: Internal details (may contain sensitive data)
        :param safe_details: Safe details for logging/display
        :raises ValueError: If message is too long
        """
        # Validate and truncate message
        if not isinstance(message, str):
            message = str(message)

        if len(message) > _MAX_MESSAGE_LENGTH:
            message = message[:_MAX_MESSAGE_LENGTH] + "..."

        self._message = message
        super().__init__(message)

        # Store immutable copies of details
        self._details: dict[str, Any] = dict(details) if details else {}
        self._safe_details: dict[str, Any] = dict(safe_details) if safe_details else {}

    @property
    def details(self) -> dict[str, Any]:
        """Get internal details (read-only).

        WARNING: Use with caution, may contain sensitive data.

        :return: Internal details dictionary (copy for safety)
        """
        return self._details.copy()

    @property
    def safe_details(self) -> dict[str, Any]:
        """Get safe details for logging/display (read-only).

        :return: Safe details dictionary (copy for safety)
        """
        return self._safe_details.copy()

    def _format_details(self) -> str:
        """Format safe details for string representation.

        :return: Formatted details string
        """
        if not self._safe_details:
            return ""

        parts = [f"{k}={v}" for k, v in self._safe_details.items()]
        return f" ({', '.join(parts)})"

    def __str__(self) -> str:
        """Safe string representation using safe_details.

        :return: String representation
        """
        return f"{self._message}{self._format_details()}"

    def __repr__(self) -> str:
        """Safe repr without sensitive data.

        :return: String representation
        """
        class_name = self.__class__.__name__
        return f"{class_name}({self._message!r})"


class APIError(OutlineError):
    """API request failure.

    Automatically determines retry eligibility based on HTTP status code.
    """

    __slots__ = ("endpoint", "response_data", "status_code")

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize API error.

        :param message: Error message
        :param status_code: HTTP status code
        :param endpoint: API endpoint
        :param response_data: Response data (may contain sensitive info)
        """
        # Import here to avoid circular dependency
        from .common_types import Constants, Validators

        # Sanitize endpoint for safe logging
        safe_endpoint = (
            Validators.sanitize_endpoint_for_logging(endpoint) if endpoint else None
        )

        # Build safe details
        safe_details: dict[str, Any] = {}
        if status_code is not None:
            safe_details["status_code"] = status_code
        if safe_endpoint is not None:
            safe_details["endpoint"] = safe_endpoint

        # Build internal details
        details: dict[str, Any] = {}
        if status_code is not None:
            details["status_code"] = status_code
        if endpoint is not None:
            details["endpoint"] = endpoint

        super().__init__(message, details=details, safe_details=safe_details)

        # Store attributes
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_data = response_data

        # Determine retry eligibility
        self.is_retryable = (
            status_code in Constants.RETRY_STATUS_CODES if status_code else False
        )

    @property
    def is_client_error(self) -> bool:
        """Check if this is a client error (4xx).

        :return: True if client error
        """
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        """Check if this is a server error (5xx).

        :return: True if server error
        """
        return self.status_code is not None and 500 <= self.status_code < 600

    @property
    def is_rate_limit_error(self) -> bool:
        """Check if this is a rate limit error (429).

        :return: True if rate limit error
        """
        return self.status_code == 429


class CircuitOpenError(OutlineError):
    """Circuit breaker is open.

    Indicates the circuit breaker has opened due to repeated failures.
    Clients should wait for retry_after seconds before retrying.
    """

    __slots__ = ("retry_after",)

    is_retryable: ClassVar[bool] = True

    def __init__(self, message: str, *, retry_after: float = 60.0) -> None:
        """Initialize circuit open error.

        :param message: Error message
        :param retry_after: Seconds to wait before retry
        :raises ValueError: If retry_after is negative
        """
        if retry_after < 0:
            raise ValueError("retry_after must be non-negative")

        safe_details = {"retry_after": round(retry_after, 2)}
        super().__init__(message, safe_details=safe_details)

        self.retry_after = retry_after
        self.default_retry_delay = retry_after


class ConfigurationError(OutlineError):
    """Configuration validation error.

    Raised when configuration is invalid or missing required fields.
    """

    __slots__ = ("field", "security_issue")

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        security_issue: bool = False,
    ) -> None:
        """Initialize configuration error.

        :param message: Error message
        :param field: Configuration field name
        :param security_issue: Whether this is a security issue
        """
        safe_details: dict[str, Any] = {}
        if field:
            safe_details["field"] = field
        if security_issue:
            safe_details["security_issue"] = True

        super().__init__(message, safe_details=safe_details)

        self.field = field
        self.security_issue = security_issue


class ValidationError(OutlineError):
    """Data validation error.

    Raised when data fails validation against expected schema.
    """

    __slots__ = ("field", "model")

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize validation error.

        :param message: Error message
        :param field: Field name that failed validation
        :param model: Model name
        """
        safe_details: dict[str, Any] = {}
        if field:
            safe_details["field"] = field
        if model:
            safe_details["model"] = model

        super().__init__(message, safe_details=safe_details)

        self.field = field
        self.model = model


class ConnectionError(OutlineError):
    """Connection failure.

    Raised when unable to establish connection to the server.
    """

    __slots__ = ("host", "port")

    is_retryable: ClassVar[bool] = True
    default_retry_delay: ClassVar[float] = 2.0

    def __init__(
        self,
        message: str,
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """Initialize connection error.

        :param message: Error message
        :param host: Host that failed
        :param port: Port that failed
        """
        safe_details: dict[str, Any] = {}
        if host:
            safe_details["host"] = host
        if port is not None:
            safe_details["port"] = port

        super().__init__(message, safe_details=safe_details)

        self.host = host
        self.port = port


class TimeoutError(OutlineError):
    """Operation timeout.

    Raised when an operation exceeds its allocated time.
    """

    __slots__ = ("operation", "timeout")

    is_retryable: ClassVar[bool] = True
    default_retry_delay: ClassVar[float] = 2.0

    def __init__(
        self,
        message: str,
        *,
        timeout: float | None = None,
        operation: str | None = None,
    ) -> None:
        """Initialize timeout error.

        :param message: Error message
        :param timeout: Timeout value in seconds
        :param operation: Operation that timed out
        """
        safe_details: dict[str, Any] = {}
        if timeout is not None:
            safe_details["timeout"] = round(timeout, 2)
        if operation:
            safe_details["operation"] = operation

        super().__init__(message, safe_details=safe_details)

        self.timeout = timeout
        self.operation = operation


# ===== Utility Functions =====


def get_retry_delay(error: Exception) -> float | None:
    """Get suggested retry delay for an error.

    :param error: Exception to check
    :return: Retry delay in seconds or None if not retryable
    """
    if not isinstance(error, OutlineError):
        return None
    if not error.is_retryable:
        return None
    return getattr(error, "default_retry_delay", 1.0)


def is_retryable(error: Exception) -> bool:
    """Check if error is retryable.

    :param error: Exception to check
    :return: True if retryable
    """
    if isinstance(error, OutlineError):
        return error.is_retryable
    return False


def get_safe_error_dict(error: Exception) -> dict[str, Any]:
    """Get safe error dictionary for logging/monitoring.

    Returns only safe information without sensitive data.

    :param error: Exception to convert
    :return: Safe error dictionary
    """
    result: dict[str, Any] = {
        "type": type(error).__name__,
        "message": str(error),
    }

    if isinstance(error, OutlineError):
        result["retryable"] = error.is_retryable
        result["retry_delay"] = error.default_retry_delay
        result["safe_details"] = error.safe_details

        # Add specific error attributes using pattern matching
        match error:
            case APIError():
                result.update(
                    {
                        "status_code": error.status_code,
                        "is_client_error": error.is_client_error,
                        "is_server_error": error.is_server_error,
                    }
                )
            case CircuitOpenError():
                result["retry_after"] = error.retry_after
            case ConfigurationError():
                result.update(
                    {
                        "field": error.field,
                        "security_issue": error.security_issue,
                    }
                )
            case ValidationError():
                result.update(
                    {
                        "field": error.field,
                        "model": error.model,
                    }
                )
            case ConnectionError():
                result.update(
                    {
                        "host": error.host,
                        "port": error.port,
                    }
                )
            case TimeoutError():
                result.update(
                    {
                        "timeout": error.timeout,
                        "operation": error.operation,
                    }
                )

    return result


def format_error_chain(error: Exception) -> list[dict[str, Any]]:
    """Format exception chain for structured logging.

    :param error: Exception to format
    :return: List of error dictionaries (root to leaf)
    """
    chain: list[dict[str, Any]] = []
    current: Exception | None = error

    while current is not None:
        chain.append(get_safe_error_dict(current))
        current = current.__cause__ or current.__context__

    return chain


__all__ = [
    "APIError",
    "CircuitOpenError",
    "ConfigurationError",
    "ConnectionError",
    "OutlineError",
    "TimeoutError",
    "ValidationError",
    "format_error_chain",
    "get_retry_delay",
    "get_safe_error_dict",
    "is_retryable",
]
