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

from typing import Optional


class OutlineError(Exception):
    """Base exception for Outline client errors."""


class APIError(OutlineError):
    """Raised when API requests fail."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        attempt: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempt = attempt

    def __str__(self) -> str:
        msg = super().__str__()
        if self.attempt is not None:
            msg = f"[Attempt {self.attempt}] {msg}"
        return msg
