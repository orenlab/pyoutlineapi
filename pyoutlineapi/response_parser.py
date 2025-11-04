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
from typing import TYPE_CHECKING, Final, TypeVar, overload

from pydantic import BaseModel, ValidationError

from .common_types import JsonDict, Constants
from .exceptions import ValidationError as OutlineValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Type aliases
T = TypeVar("T", bound=BaseModel)

# Constants for optimization
_MAX_LOGGED_ERRORS: Final[int] = 10
_ERROR_FIELDS: Final[tuple[str, ...]] = ("error", "message", "error_message", "msg")


class ResponseParser:
    """High-performance utility class for parsing and validating API responses."""

    __slots__ = ()  # Stateless class - zero memory overhead

    @staticmethod
    @overload
    def parse(
        data: dict[str, object],
        model: type[T],
        *,
        as_json: bool = True,
    ) -> JsonDict: ...

    @staticmethod
    @overload
    def parse(
        data: dict[str, object],
        model: type[T],
        *,
        as_json: bool = False,
    ) -> T: ...

    @staticmethod
    def parse(
        data: dict[str, object],
        model: type[T],
        *,
        as_json: bool = False,
    ) -> T | JsonDict:
        """Parse and validate response data with comprehensive error handling.

        Type-safe overloads ensure correct return type based on as_json parameter.

        :param data: Raw response data from API
        :param model: Pydantic model class for validation
        :param as_json: Return raw JSON dict instead of model instance
        :return: Validated model instance or JSON dict
        :raises ValidationError: If validation fails with detailed error info

        Example:
            >>> data = {"name": "test", "id": 123}
            >>> # Type-safe: returns MyModel instance
            >>> result = ResponseParser.parse(data, MyModel, as_json=False)
            >>> # Type-safe: returns dict
            >>> json_result = ResponseParser.parse(data, MyModel, as_json=True)
        """
        if not isinstance(data, dict):
            raise OutlineValidationError(
                f"Expected dict, got {type(data).__name__}",
                model=model.__name__,
            )

        if not data and logger.isEnabledFor(Constants.LOG_LEVEL_DEBUG):
            logger.debug("Parsing empty dict for model %s", model.__name__)

        try:
            data_dict = data if isinstance(data, dict) else dict(data)
            validated = model.model_validate(data_dict)

            if as_json:
                return validated.model_dump(by_alias=True)
            return validated

        except ValidationError as e:
            errors = e.errors()

            if not errors:
                raise OutlineValidationError(
                    "Validation failed with no error details",
                    model=model.__name__,
                ) from e

            first_error = errors[0]
            field = ".".join(str(loc) for loc in first_error.get("loc", ()))
            message = first_error.get("msg", "Validation failed")

            error_count = len(errors)
            if error_count > 1:
                if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                    logger.warning(
                        "Multiple validation errors for %s: %d error(s)",
                        model.__name__,
                        error_count,
                    )

                if logger.isEnabledFor(Constants.LOG_LEVEL_DEBUG):
                    logger.debug("Validation error details:")
                    logged_count = min(error_count, _MAX_LOGGED_ERRORS)

                    for i, error in enumerate(errors[:logged_count], 1):
                        error_field = ".".join(str(loc) for loc in error.get("loc", ()))
                        error_msg = error.get("msg", "Unknown error")
                        logger.debug("  %d. %s: %s", i, error_field, error_msg)

                    if error_count > _MAX_LOGGED_ERRORS:
                        remaining = error_count - _MAX_LOGGED_ERRORS
                        logger.debug("  ... and %d more error(s)", remaining)

            raise OutlineValidationError(
                message,
                field=field,
                model=model.__name__,
            ) from e

        except Exception as e:
            # Catch any other unexpected errors during validation
            if logger.isEnabledFor(Constants.LOG_LEVEL_ERROR):
                logger.error(
                    "Unexpected error during validation: %s",
                    e,
                    exc_info=True,
                )
            raise OutlineValidationError(
                f"Unexpected error during validation: {e}",
                model=model.__name__,
            ) from e

    @staticmethod
    def parse_simple(data: dict[str, object]) -> bool:
        """Parse simple success/error responses efficiently.

        Handles various response formats with minimal overhead:
        - {"success": true/false}
        - {"error": "..."}  → False
        - {"message": "..."}  → False
        - Empty dict  → True (assumed success)

        :param data: Response data
        :return: True if successful, False otherwise

        Example:
            >>> ResponseParser.parse_simple({"success": True})
            True
            >>> ResponseParser.parse_simple({"error": "Something failed"})
            False
            >>> ResponseParser.parse_simple({})
            True
        """
        if not isinstance(data, dict):
            if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                logger.warning(
                    "Expected dict in parse_simple, got %s",
                    type(data).__name__,
                )
            return False

        if "success" in data:
            success = data["success"]
            if not isinstance(success, bool):
                if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                    logger.warning(
                        "success field is not bool: %s, coercing to bool",
                        type(success).__name__,
                    )
                return bool(success)
            return success

        return "error" not in data and "message" not in data

    @staticmethod
    def validate_response_structure(
        data: dict[str, object],
        required_fields: Sequence[str] | None = None,
    ) -> bool:
        """Validate response structure without full parsing.

        Lightweight validation before expensive Pydantic validation.
        Useful for early rejection of malformed responses.

        :param data: Response data to validate
        :param required_fields: Sequence of required field names
        :return: True if structure is valid

        Example:
            >>> data = {"id": 1, "name": "test"}
            >>> ResponseParser.validate_response_structure(data, ["id", "name"])
            True
            >>> ResponseParser.validate_response_structure(data, ["id", "missing"])
            False
        """
        if not isinstance(data, dict):
            return False

        if not data and not required_fields:
            return True

        if not required_fields:
            return True

        return all(field in data for field in required_fields)

    @staticmethod
    def extract_error_message(data: dict[str, object]) -> str | None:
        """Extract error message from response data efficiently.

        Checks common error field names in order of preference.
        Uses pre-computed tuple for fast iteration.

        :param data: Response data
        :return: Error message or None if not found

        Example:
            >>> ResponseParser.extract_error_message({"error": "Not found"})
            'Not found'
            >>> ResponseParser.extract_error_message({"message": "Failed"})
            'Failed'
            >>> ResponseParser.extract_error_message({"success": True})
            None
        """
        if not isinstance(data, dict):
            return None

        for field in _ERROR_FIELDS:
            if field in data:
                value = data[field]
                # Fast path: already a string
                if isinstance(value, str):
                    return value
                # Convert non-string to string (None → None)
                return str(value) if value is not None else None

        return None

    @staticmethod
    def is_error_response(data: dict[str, object]) -> bool:
        """Check if response indicates an error efficiently.

        Fast boolean check for error indicators in response.

        :param data: Response data
        :return: True if response indicates an error

        Example:
            >>> ResponseParser.is_error_response({"error": "Failed"})
            True
            >>> ResponseParser.is_error_response({"success": False})
            True
            >>> ResponseParser.is_error_response({"success": True})
            False
            >>> ResponseParser.is_error_response({})
            False
        """
        if not isinstance(data, dict):
            return False

        if "error" in data or "error_message" in data:
            return True

        if "success" in data:
            success = data["success"]
            return success is False

        # No error indicators found
        return False


__all__ = [
    "JsonDict",
    "ResponseParser",
]
