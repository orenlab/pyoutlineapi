"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Simple response parser with validation.

Provides utilities for parsing and validating API responses,
converting between raw JSON and Pydantic models.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ValidationError

from .exceptions import ValidationError as OutlineValidationError

logger = logging.getLogger(__name__)

# Type aliases
JsonDict = dict[str, Any]
T = TypeVar("T", bound=BaseModel)


class ResponseParser:
    """
    Utility class for parsing and validating API responses.

    Provides methods to convert raw API responses to validated
    Pydantic models or JSON dictionaries.

    Example:
        >>> from pyoutlineapi.response_parser import ResponseParser
        >>> from pyoutlineapi.models import Server
        >>>
        >>> # Parse to model
        >>> data = {"name": "My Server", "serverId": "abc123", ...}
        >>> server = ResponseParser.parse(data, Server)
        >>> print(f"Server: {server.name}")
        >>>
        >>> # Parse to JSON dict
        >>> server_dict = ResponseParser.parse(data, Server, as_json=True)
        >>> print(f"Server: {server_dict['name']}")
    """

    @staticmethod
    @overload
    def parse(
        data: dict[str, Any],
        model: type[T],
        *,
        as_json: bool = True,
    ) -> JsonDict: ...

    @staticmethod
    @overload
    def parse(
        data: dict[str, Any],
        model: type[T],
        *,
        as_json: bool = False,
    ) -> T: ...

    @staticmethod
    def parse(
        data: dict[str, Any],
        model: type[T],
        *,
        as_json: bool = False,
    ) -> T | JsonDict:
        """
        Parse and validate response data.

        Validates the response against a Pydantic model and returns
        either the validated model or a JSON dictionary.

        Args:
            data: Raw response data dictionary
            model: Pydantic model class for validation
            as_json: Return as JSON dict instead of model (default: False)

        Returns:
            T | JsonDict: Validated model or JSON dict

        Raises:
            OutlineValidationError: If validation fails

        Example:
            >>> from pyoutlineapi.models import AccessKey
            >>>
            >>> # Response from API
            >>> response_data = {
            ...     "id": "1",
            ...     "name": "Alice",
            ...     "password": "secret",
            ...     "port": 8388,
            ...     "method": "chacha20-ietf-poly1305",
            ...     "accessUrl": "ss://...",
            ... }
            >>>
            >>> # Parse to model
            >>> key = ResponseParser.parse(response_data, AccessKey)
            >>> print(f"Key: {key.name} (ID: {key.id})")
            >>>
            >>> # Parse to JSON dict
            >>> key_dict = ResponseParser.parse(response_data, AccessKey, as_json=True)
            >>> print(f"Key: {key_dict['name']}")
        """
        try:
            # Validate with model
            validated = model.model_validate(data)

            # Return format
            if as_json:
                return validated.model_dump(by_alias=True)
            return validated

        except ValidationError as e:
            # Convert to our exception type
            errors = e.errors()
            if errors:
                first_error = errors[0]
                field = ".".join(str(loc) for loc in first_error.get("loc", []))
                message = first_error.get("msg", "Validation failed")

                raise OutlineValidationError(
                    message,
                    field=field,
                    model=model.__name__,
                ) from e

            raise OutlineValidationError(
                "Validation failed",
                model=model.__name__,
            ) from e

    @staticmethod
    def parse_simple(data: dict[str, Any]) -> bool:
        """
        Parse simple success responses.

        Checks for explicit success flag or assumes success
        if no errors are present.

        Args:
            data: Response data dictionary

        Returns:
            bool: True if successful

        Example:
            >>> # Explicit success
            >>> ResponseParser.parse_simple({"success": True})
            True
            >>>
            >>> # Implicit success (no errors)
            >>> ResponseParser.parse_simple({})
            True
            >>>
            >>> # Failed
            >>> ResponseParser.parse_simple({"success": False})
            False
        """
        # Check explicit success field
        if "success" in data:
            return bool(data["success"])

        # Empty dict or any dict without errors is success
        return True


__all__ = [
    "ResponseParser",
    "JsonDict",
]
