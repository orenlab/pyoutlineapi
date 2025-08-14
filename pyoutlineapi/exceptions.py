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

from typing import Any


class OutlineError(Exception):
    """Base exception for Outline client errors."""


class APIError(OutlineError):
    """Raised when API requests fail."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        attempt: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempt = attempt

    def __str__(self) -> str:
        msg = super().__str__()
        if self.attempt is not None:
            msg = f"[Attempt {self.attempt}] {msg}"
        return msg


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors."""

    pass


class CircuitOpenError(CircuitBreakerError):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ConfigurationError(OutlineError):
    """Configuration-related errors."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        self.field = field
        self.value = value
        super().__init__(message)

    def __str__(self) -> str:
        if self.field:
            return f"Configuration error in '{self.field}': {super().__str__()}"
        return super().__str__()


class ValidationError(ValueError):
    """Enhanced validation error with field information."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        self.field = field
        self.value = value
        super().__init__(message)

    def __str__(self) -> str:
        if self.field:
            return f"Validation error in field '{self.field}': {super().__str__()}"
        return super().__str__()


__all__ = [
    "OutlineError",
    "APIError",
    "CircuitBreakerError",
    "CircuitOpenError",
    "ConfigurationError",
    "ValidationError",
]
