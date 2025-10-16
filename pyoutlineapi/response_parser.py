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

import logging
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ValidationError

from .exceptions import ValidationError as OutlineValidationError

logger = logging.getLogger(__name__)

# Type aliases
JsonDict = dict[str, Any]
T = TypeVar("T", bound=BaseModel)


class ResponseParser:
    """Utility class for parsing and validating API responses."""

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
        """Parse and validate response data."""
        if not isinstance(data, dict):
            raise OutlineValidationError(
                f"Expected dict, got {type(data).__name__}",
                model=model.__name__,
            )

        try:
            # Validate with model
            validated = model.model_validate(data)

            # Return format
            if as_json:
                return validated.model_dump(by_alias=True)
            return validated

        except ValidationError as e:
            # Convert to our exception type with enhanced error reporting
            errors = e.errors()

            if not errors:
                raise OutlineValidationError(
                    "Validation failed",
                    model=model.__name__,
                ) from e

            # Get first error for primary message
            first_error = errors[0]
            field = ".".join(str(loc) for loc in first_error.get("loc", []))
            message = first_error.get("msg", "Validation failed")

            # Log all errors for debugging
            if len(errors) > 1:
                logger.warning(
                    f"Multiple validation errors for {model.__name__}: "
                    f"{len(errors)} errors"
                )
                for i, error in enumerate(errors, 1):
                    error_field = ".".join(str(loc) for loc in error.get("loc", []))
                    error_msg = error.get("msg", "Unknown error")
                    logger.debug(f"  {i}. {error_field}: {error_msg}")

            raise OutlineValidationError(
                message,
                field=field,
                model=model.__name__,
            ) from e

    @staticmethod
    def parse_simple(data: dict[str, Any]) -> bool:
        """Parse simple success responses."""
        if not isinstance(data, dict):
            logger.warning(f"Expected dict in parse_simple, got {type(data).__name__}")
            return False

        # Check explicit success field
        if "success" in data:
            success = data["success"]
            if not isinstance(success, bool):
                logger.warning(f"success field is not bool: {type(success).__name__}")
                return bool(success)
            return success

        # Check for error indicators
        if "error" in data or "message" in data:
            return False

        # Empty dict or any dict without errors is success
        return True

    @staticmethod
    def validate_response_structure(
        data: dict[str, Any],
        required_fields: list[str] | None = None,
    ) -> bool:
        """Validate response structure without full parsing."""
        if not isinstance(data, dict):
            return False

        if required_fields:
            return all(field in data for field in required_fields)

        return True


__all__ = [
    "JsonDict",
    "ResponseParser",
]
