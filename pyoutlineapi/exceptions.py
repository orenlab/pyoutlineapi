"""Exception hierarchy for PyOutlineAPI.

Provides structured exceptions with rich error context, retry guidance,
and credential sanitization for secure error handling.

Classes:
    OutlineError: Base exception with context and retry support
    APIError: HTTP API failures with status codes
    CircuitOpenError: Circuit breaker open state
    ConfigurationError: Invalid configuration
    ValidationError: Data validation failures
    OutlineConnectionError: Network connection issues
    OutlineTimeoutError: Operation timeouts

Functions:
    get_retry_delay: Get suggested retry delay for an error
    is_retryable: Check if error should be retried
    get_safe_error_dict: Extract safe error info for logging
    format_error_chain: Format exception chain for structured logging

License:
    MIT License - Copyright (c) 2025 Denis Rozhnovskiy

Repository:
    https://github.com/orenlab/pyoutlineapi
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, ClassVar, Final

from .common_types import Constants, CredentialSanitizer

# Maximum length for error messages to prevent DoS
_MAX_MESSAGE_LENGTH: Final[int] = 1024

_EMPTY_DICT: Final[MappingProxyType[str, Any]] = MappingProxyType({})


class OutlineError(Exception):
    """Base exception for all PyOutlineAPI errors.

    Provides rich error context, retry guidance, and safe serialization
    with automatic credential sanitization.

    Attributes:
        is_retryable: Whether this error type should be retried
        default_retry_delay: Suggested delay before retry in seconds

    Example:
        >>> try:
        ...     raise OutlineError("Connection failed", details={"host": "server"})
        ... except OutlineError as e:
        ...     print(e.safe_details)  # {'host': 'server'}
    """

    __slots__ = ("_cached_str", "_details", "_message", "_safe_details")

    _is_retryable: ClassVar[bool] = False
    _default_retry_delay: ClassVar[float] = 1.0

    def __init__(
        self,
        message: object,
        *,
        details: dict[str, Any] | None = None,
        safe_details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize exception with automatic credential sanitization.

        Args:
            message: Error message (automatically sanitized)
            details: Internal details (may contain sensitive data)
            safe_details: Safe details for logging/display

        Raises:
            ValueError: If message exceeds maximum length after sanitization
        """
        # Validate and sanitize message
        if not isinstance(message, str):
            message = str(message)

        # Sanitize credentials from message
        sanitized_message = CredentialSanitizer.sanitize(message)

        # Truncate if too long
        if len(sanitized_message) > _MAX_MESSAGE_LENGTH:
            sanitized_message = sanitized_message[:_MAX_MESSAGE_LENGTH] + "..."

        self._message = sanitized_message
        super().__init__(sanitized_message)

        self._details: dict[str, Any] | MappingProxyType[str, Any] = (
            dict(details) if details else _EMPTY_DICT
        )
        self._safe_details: dict[str, Any] | MappingProxyType[str, Any] = (
            dict(safe_details) if safe_details else _EMPTY_DICT
        )

        self._cached_str: str | None = None

    @property
    def details(self) -> dict[str, Any]:
        """Get internal error details (may contain sensitive data).

        Warning:
            Use with caution - may contain credentials or sensitive information.
            For logging, use ``safe_details`` instead.

        Returns:
            Copy of internal details dictionary
        """
        if self._details is _EMPTY_DICT:
            return {}
        return self._details.copy()

    @property
    def safe_details(self) -> dict[str, Any]:
        """Get sanitized error details safe for logging.

        Returns:
            Copy of safe details dictionary
        """
        if self._safe_details is _EMPTY_DICT:
            return {}
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

        Cached for performance on repeated access.

        :return: String representation
        """
        if self._cached_str is None:
            self._cached_str = f"{self._message}{self._format_details()}"
        return self._cached_str

    def __repr__(self) -> str:
        """Safe repr without sensitive data.

        :return: String representation
        """
        class_name = self.__class__.__name__
        return f"{class_name}({self._message!r})"

    @property
    def is_retryable(self) -> bool:
        """Return whether this error type should be retried."""
        return self._is_retryable

    @property
    def default_retry_delay(self) -> float:
        """Return suggested delay before retry in seconds."""
        return self._default_retry_delay


class APIError(OutlineError):
    """HTTP API request failure.

    Automatically determines retry eligibility based on HTTP status code.

    Attributes:
        status_code: HTTP status code (if available)
        endpoint: API endpoint that failed
        response_data: Raw response data (may contain sensitive info)

    Example:
        >>> error = APIError("Not found", status_code=404, endpoint="/server")
        >>> error.is_client_error  # True
        >>> error.is_retryable  # False
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
        """Initialize API error with sanitized endpoint.

        Args:
            message: Error message
            status_code: HTTP status code
            endpoint: API endpoint (will be sanitized)
            response_data: Response data (may contain sensitive info)
        """
        from .common_types import Validators

        # Sanitize endpoint for safe logging
        safe_endpoint = (
            Validators.sanitize_endpoint_for_logging(endpoint) if endpoint else None
        )

        # Build safe details (optimization: avoid dict creation if all None)
        safe_details: dict[str, Any] | None = None
        if status_code is not None or safe_endpoint is not None:
            safe_details = {}
            if status_code is not None:
                safe_details["status_code"] = status_code
            if safe_endpoint is not None:
                safe_details["endpoint"] = safe_endpoint

        # Build internal details (optimization: avoid dict creation if all None)
        details: dict[str, Any] | None = None
        if status_code is not None or endpoint is not None:
            details = {}
            if status_code is not None:
                details["status_code"] = status_code
            if endpoint is not None:
                details["endpoint"] = endpoint

        super().__init__(message, details=details, safe_details=safe_details)

        # Store attributes directly (faster access than dict lookups)
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_data = response_data

    @property
    def is_retryable(self) -> bool:
        """Check if error is retryable based on status code."""
        return (
            self.status_code in Constants.RETRY_STATUS_CODES
            if self.status_code
            else False
        )

    @property
    def is_client_error(self) -> bool:
        """Check if error is a client error (4xx status).

        Returns:
            True if status code is 400-499
        """
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        """Check if error is a server error (5xx status).

        Returns:
            True if status code is 500-599
        """
        return self.status_code is not None and 500 <= self.status_code < 600

    @property
    def is_rate_limit_error(self) -> bool:
        """Check if error is a rate limit error (429 status).

        Returns:
            True if status code is 429
        """
        return self.status_code == 429


class CircuitOpenError(OutlineError):
    """Circuit breaker is open due to repeated failures.

    Indicates temporary service unavailability. Clients should wait
    for ``retry_after`` seconds before retrying.

    Attributes:
        retry_after: Seconds to wait before retry

    Example:
        >>> error = CircuitOpenError("Circuit open", retry_after=60.0)
        >>> error.is_retryable  # True
        >>> error.retry_after  # 60.0
    """

    __slots__ = ("retry_after",)

    _is_retryable: ClassVar[bool] = True

    def __init__(self, message: str, *, retry_after: float = 60.0) -> None:
        """Initialize circuit open error.

        Args:
            message: Error message
            retry_after: Seconds to wait before retry

        Raises:
            ValueError: If retry_after is negative
        """
        if retry_after < 0:
            raise ValueError("retry_after must be non-negative")

        # Pre-round for safe_details (avoid repeated rounding)
        rounded_retry = round(retry_after, 2)
        safe_details = {"retry_after": rounded_retry}
        super().__init__(message, safe_details=safe_details)

        self.retry_after = retry_after

    @property
    def default_retry_delay(self) -> float:
        """Suggested delay before retry."""
        return self.retry_after


class ConfigurationError(OutlineError):
    """Invalid or missing configuration.

    Attributes:
        field: Configuration field name that failed
        security_issue: Whether this is a security-related issue

    Example:
        >>> error = ConfigurationError(
        ...     "Missing API URL", field="api_url", security_issue=True
        ... )
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

        Args:
            message: Error message
            field: Configuration field name
            security_issue: Whether this is a security issue
        """
        safe_details: dict[str, Any] | None = None
        if field or security_issue:
            safe_details = {}
            if field:
                safe_details["field"] = field
            if security_issue:
                safe_details["security_issue"] = True

        super().__init__(message, safe_details=safe_details)

        self.field = field
        self.security_issue = security_issue


class ValidationError(OutlineError):
    """Data validation failure.

    Raised when data fails validation against expected schema.

    Attributes:
        field: Field name that failed validation
        model: Model name

    Example:
        >>> error = ValidationError(
        ...     "Invalid port number", field="port", model="ServerConfig"
        ... )
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

        Args:
            message: Error message
            field: Field name that failed validation
            model: Model name
        """
        safe_details: dict[str, Any] | None = None
        if field or model:
            safe_details = {}
            if field:
                safe_details["field"] = field
            if model:
                safe_details["model"] = model

        super().__init__(message, safe_details=safe_details)

        self.field = field
        self.model = model


class OutlineConnectionError(OutlineError):
    """Network connection failure.

    Attributes:
        host: Host that failed
        port: Port that failed

    Example:
        >>> error = OutlineConnectionError(
        ...     "Connection refused", host="server.com", port=443
        ... )
        >>> error.is_retryable  # True
    """

    __slots__ = ("host", "port")

    _is_retryable: ClassVar[bool] = True
    _default_retry_delay: ClassVar[float] = 2.0

    def __init__(
        self,
        message: str,
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """Initialize connection error.

        Args:
            message: Error message
            host: Host that failed
            port: Port that failed
        """
        safe_details: dict[str, Any] | None = None
        if host or port is not None:
            safe_details = {}
            if host:
                safe_details["host"] = host
            if port is not None:
                safe_details["port"] = port

        super().__init__(message, safe_details=safe_details)

        self.host = host
        self.port = port


class OutlineTimeoutError(OutlineError):
    """Operation timeout.

    Attributes:
        timeout: Timeout value in seconds
        operation: Operation that timed out

    Example:
        >>> error = OutlineTimeoutError(
        ...     "Request timeout", timeout=30.0, operation="get_server_info"
        ... )
        >>> error.is_retryable  # True
    """

    __slots__ = ("operation", "timeout")

    _is_retryable: ClassVar[bool] = True
    _default_retry_delay: ClassVar[float] = 2.0

    def __init__(
        self,
        message: str,
        *,
        timeout: float | None = None,
        operation: str | None = None,
    ) -> None:
        """Initialize timeout error.

        Args:
            message: Error message
            timeout: Timeout value in seconds
            operation: Operation that timed out
        """
        safe_details: dict[str, Any] | None = None
        if timeout is not None or operation:
            safe_details = {}
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

    Args:
        error: Exception to check

    Returns:
        Retry delay in seconds, or None if not retryable

    Example:
        >>> error = OutlineTimeoutError("Timeout")
        >>> get_retry_delay(error)  # 2.0
    """
    if not isinstance(error, OutlineError):
        return None
    if not error.is_retryable:
        return None
    return error.default_retry_delay


def is_retryable(error: Exception) -> bool:
    """Check if error should be retried.

    Args:
        error: Exception to check

    Returns:
        True if error is retryable

    Example:
        >>> error = APIError("Server error", status_code=503)
        >>> is_retryable(error)  # True
    """
    if isinstance(error, OutlineError):
        return error.is_retryable
    return False


def get_safe_error_dict(error: BaseException) -> dict[str, Any]:
    """Extract safe error information for logging.

    Returns only safe information without sensitive data.

    Args:
        error: Exception to convert

    Returns:
        Safe error dictionary suitable for logging

    Example:
        >>> error = APIError("Not found", status_code=404)
        >>> get_safe_error_dict(error)
        {'type': 'APIError', 'message': 'Not found', 'status_code': 404, ...}
    """
    result: dict[str, Any] = {
        "type": type(error).__name__,
        "message": str(error),
    }

    if not isinstance(error, OutlineError):
        return result

    result.update(
        {
            "retryable": error.is_retryable,
            "retry_delay": error.default_retry_delay,
            "safe_details": error.safe_details,
        }
    )

    match error:
        case APIError():
            result["status_code"] = error.status_code
            # Only compute these if status_code is not None
            if error.status_code is not None:
                result["is_client_error"] = error.is_client_error
                result["is_server_error"] = error.is_server_error
        case CircuitOpenError():
            result["retry_after"] = error.retry_after
        case ConfigurationError():
            if error.field is not None:
                result["field"] = error.field
            result["security_issue"] = error.security_issue
        case ValidationError():
            if error.field is not None:
                result["field"] = error.field
            if error.model is not None:
                result["model"] = error.model
        case OutlineConnectionError():
            if error.host is not None:
                result["host"] = error.host
            if error.port is not None:
                result["port"] = error.port
        case OutlineTimeoutError():
            if error.timeout is not None:
                result["timeout"] = error.timeout
            if error.operation is not None:
                result["operation"] = error.operation

    return result


def format_error_chain(error: Exception) -> list[dict[str, Any]]:
    """Format exception chain for structured logging.

    Args:
        error: Exception to format

    Returns:
        List of error dictionaries ordered from root to leaf

    Example:
        >>> try:
        ...     raise ValueError("Inner") from KeyError("Outer")
        ... except Exception as e:
        ...     chain = format_error_chain(e)
        ...     len(chain)  # 2
    """
    # Pre-allocate with reasonable size hint (most chains are 1-3 errors)
    chain: list[dict[str, Any]] = []
    current: BaseException | None = error

    while current is not None:
        chain.append(get_safe_error_dict(current))
        current = current.__cause__ or current.__context__

    return chain


__all__ = [
    "APIError",
    "CircuitOpenError",
    "ConfigurationError",
    "OutlineConnectionError",
    "OutlineError",
    "OutlineTimeoutError",
    "ValidationError",
    "format_error_chain",
    "get_retry_delay",
    "get_safe_error_dict",
    "is_retryable",
]
