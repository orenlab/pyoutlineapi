"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutlineAPI project.

PyOutlineAPI is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""


class APIError(Exception):
    """Base class for all API-related errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


class HTTPError(APIError):
    """Raised for HTTP-related errors (e.g., HTTP status codes)."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)

    def __str__(self):
        return f"HTTP error occurred: {self.status_code} - {self.message}"


class RequestError(APIError):
    """Raised for request-related errors (e.g., connection issues)."""

    def __init__(self, message: str):
        super().__init__(f"An error occurred while requesting data: {message}")


class ValidationError(APIError):
    """Raised for validation errors when processing API responses."""

    def __init__(self, message: str):
        super().__init__(f"Validation error occurred: {message}")
