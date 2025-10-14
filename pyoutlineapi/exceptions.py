"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Modern exception hierarchy with enhanced error handling.

Provides a comprehensive exception hierarchy with rich error information
and retry guidance.
"""

from __future__ import annotations

from typing import Any, ClassVar


class OutlineError(Exception):
    """
    Base exception for all PyOutlineAPI errors.

    Provides common interface for error handling with optional details
    and retry configuration.

    Attributes:
        details: Dictionary with additional error context
        is_retryable: Whether the error is retryable (class-level)
        default_retry_delay: Suggested retry delay in seconds (class-level)

    Example:
        >>> try:
        ...     await client.get_server_info()
        ... except OutlineError as e:
        ...     print(f"Error: {e}")
        ...     if hasattr(e, 'is_retryable') and e.is_retryable:
        ...         print(f"Can retry after {e.default_retry_delay}s")
    """

    # Class-level retry configuration
    is_retryable: ClassVar[bool] = False
    default_retry_delay: ClassVar[float] = 1.0

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """
        Initialize base exception.

        Args:
            message: Error message
            details: Additional error context
        """
        super().__init__(message)
        self.details = details or {}

    def __str__(self) -> str:
        """String representation with details if available."""
        if not self.details:
            return super().__str__()
        details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
        return f"{super().__str__()} ({details_str})"


class APIError(OutlineError):
    """
    Raised when API requests fail.

    Automatically determines if the error is retryable based on HTTP status code.

    Attributes:
        status_code: HTTP status code (e.g., 404, 500)
        endpoint: API endpoint that failed
        response_data: Raw response data (if available)

    Example:
        >>> try:
        ...     await client.get_access_key("invalid-id")
        ... except APIError as e:
        ...     print(f"API error: {e}")
        ...     print(f"Status: {e.status_code}")
        ...     print(f"Endpoint: {e.endpoint}")
        ...     if e.is_client_error:
        ...         print("Client error (4xx)")
        ...     if e.is_retryable:
        ...         print("Can retry this request")
    """

    # Retryable for specific status codes
    RETRYABLE_CODES: ClassVar[frozenset[int]] = frozenset(
        {408, 429, 500, 502, 503, 504}
    )

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code
            endpoint: API endpoint that failed
            response_data: Raw response data
        """
        details = {}
        if status_code is not None:
            details["status_code"] = status_code
        if endpoint is not None:
            details["endpoint"] = endpoint

        super().__init__(message, details=details)
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_data = response_data

        # Set retryable based on status code
        self.is_retryable = (
            status_code in self.RETRYABLE_CODES if status_code else False
        )

    @property
    def is_client_error(self) -> bool:
        """
        Check if this is a client error (4xx).

        Returns:
            bool: True if status code is 400-499

        Example:
            >>> try:
            ...     await client.get_access_key("invalid")
            ... except APIError as e:
            ...     if e.is_client_error:
            ...         print("Fix the request")
        """
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        """
        Check if this is a server error (5xx).

        Returns:
            bool: True if status code is 500-599

        Example:
            >>> try:
            ...     await client.get_server_info()
            ... except APIError as e:
            ...     if e.is_server_error:
            ...         print("Server issue, can retry")
        """
        return self.status_code is not None and 500 <= self.status_code < 600


class CircuitOpenError(OutlineError):
    """
    Raised when circuit breaker is open.

    Indicates the service is experiencing issues and requests
    are temporarily blocked to prevent cascading failures.

    Attributes:
        retry_after: Seconds to wait before retrying

    Example:
        >>> try:
        ...     await client.get_server_info()
        ... except CircuitOpenError as e:
        ...     print(f"Circuit is open")
        ...     print(f"Retry after {e.retry_after} seconds")
        ...     await asyncio.sleep(e.retry_after)
        ...     # Try again
    """

    is_retryable: ClassVar[bool] = True

    def __init__(self, message: str, *, retry_after: float = 60.0) -> None:
        """
        Initialize circuit open error.

        Args:
            message: Error message
            retry_after: Seconds to wait before retrying (default: 60.0)
        """
        super().__init__(message, details={"retry_after": retry_after})
        self.retry_after = retry_after
        self.default_retry_delay = retry_after


class ConfigurationError(OutlineError):
    """
    Configuration validation error.

    Raised when configuration is invalid or missing required fields.

    Attributes:
        field: Configuration field that caused error
        security_issue: Whether this is a security concern

    Example:
        >>> try:
        ...     config = OutlineClientConfig(
        ...         api_url="invalid",
        ...         cert_sha256=SecretStr("short"),
        ...     )
        ... except ConfigurationError as e:
        ...     print(f"Config error in field: {e.field}")
        ...     if e.security_issue:
        ...         print("⚠️ Security issue detected")
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        security_issue: bool = False,
    ) -> None:
        """
        Initialize configuration error.

        Args:
            message: Error message
            field: Configuration field name
            security_issue: Whether this is a security concern
        """
        details = {}
        if field:
            details["field"] = field
        if security_issue:
            details["security_issue"] = True

        super().__init__(message, details=details)
        self.field = field
        self.security_issue = security_issue


class ValidationError(OutlineError):
    """
    Data validation error.

    Raised when API response or request data fails validation.

    Attributes:
        field: Field that failed validation
        model: Model name

    Example:
        >>> try:
        ...     # Invalid port number
        ...     await client.set_default_port(80)
        ... except ValidationError as e:
        ...     print(f"Validation error: {e}")
        ...     print(f"Field: {e.field}")
        ...     print(f"Model: {e.model}")
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        model: str | None = None,
    ) -> None:
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Field name
            model: Model name
        """
        details = {}
        if field:
            details["field"] = field
        if model:
            details["model"] = model

        super().__init__(message, details=details)
        self.field = field
        self.model = model


class ConnectionError(OutlineError):
    """
    Connection failure error.

    Raised when unable to establish connection to the server.

    Attributes:
        host: Target hostname
        port: Target port

    Example:
        >>> try:
        ...     async with AsyncOutlineClient.from_env() as client:
        ...         await client.get_server_info()
        ... except ConnectionError as e:
        ...     print(f"Cannot connect to {e.host}:{e.port}")
        ...     if e.is_retryable:
        ...         print("Will retry automatically")
    """

    is_retryable: ClassVar[bool] = True

    def __init__(
        self,
        message: str,
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """
        Initialize connection error.

        Args:
            message: Error message
            host: Target hostname
            port: Target port
        """
        details = {}
        if host:
            details["host"] = host
        if port:
            details["port"] = port

        super().__init__(message, details=details)
        self.host = host
        self.port = port


class TimeoutError(OutlineError):
    """
    Operation timeout error.

    Raised when an operation exceeds the configured timeout.

    Attributes:
        timeout: Timeout value that was exceeded (seconds)

    Example:
        >>> try:
        ...     # With 5 second timeout
        ...     config = OutlineClientConfig.from_env()
        ...     config.timeout = 5
        ...     async with AsyncOutlineClient(config) as client:
        ...         await client.get_server_info()
        ... except TimeoutError as e:
        ...     print(f"Operation timed out after {e.timeout}s")
        ...     if e.is_retryable:
        ...         print("Can retry with longer timeout")
    """

    is_retryable: ClassVar[bool] = True

    def __init__(
        self,
        message: str,
        *,
        timeout: float | None = None,
    ) -> None:
        """
        Initialize timeout error.

        Args:
            message: Error message
            timeout: Timeout value in seconds
        """
        super().__init__(message, details={"timeout": timeout} if timeout else None)
        self.timeout = timeout


# Utility functions


def get_retry_delay(error: Exception) -> float | None:
    """
    Get suggested retry delay for an error.

    Args:
        error: Exception to check

    Returns:
        float | None: Delay in seconds, or None if not retryable

    Example:
        >>> try:
        ...     await client.get_server_info()
        ... except Exception as e:
        ...     delay = get_retry_delay(e)
        ...     if delay:
        ...         print(f"Retrying in {delay}s")
        ...         await asyncio.sleep(delay)
        ...         # Retry operation
        ...     else:
        ...         print("Error is not retryable")
    """
    if not isinstance(error, OutlineError):
        return None

    if not error.is_retryable:
        return None

    return getattr(error, "default_retry_delay", 1.0)


__all__ = [
    "OutlineError",
    "APIError",
    "CircuitOpenError",
    "ConfigurationError",
    "ValidationError",
    "ConnectionError",
    "TimeoutError",
    "get_retry_delay",
]
