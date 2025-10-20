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

from .exceptions import ValidationError as OutlineValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Type aliases
JsonDict = dict[str, object]
T = TypeVar("T", bound=BaseModel)

# Maximum number of validation errors to log
_MAX_LOGGED_ERRORS: Final[int] = 10


def _log_if_enabled(level: int, message: str, **kwargs: object) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    :param kwargs: Additional logging kwargs
    """
    if logger.isEnabledFor(level):
        logger.log(level, message, **kwargs)


class ResponseParser:
    """Utility class for parsing and validating API responses.

    Thread-safe stateless parser with comprehensive validation.
    Uses overloads for precise type hinting.
    """

    __slots__ = ()  # Stateless class

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
        """Parse and validate response data.

        :param data: Raw response data
        :param model: Pydantic model class
        :param as_json: Return raw JSON instead of model
        :return: Validated model instance or JSON dict
        :raises ValidationError: If validation fails
        """
        # Type validation
        if not isinstance(data, dict):
            raise OutlineValidationError(
                f"Expected dict, got {type(data).__name__}",
                model=model.__name__,
            )

        # Empty dict check
        if not data:
            _log_if_enabled(
                logging.DEBUG,
                f"Parsing empty dict for model {model.__name__}",
            )

        try:
            data_dict = dict(data) if not isinstance(data, dict) else data
            validated = model.model_validate(data_dict)

            if as_json:
                return validated.model_dump(by_alias=True)
            return validated

        except ValidationError as e:
            errors = e.errors()

            # Handle empty errors list
            if not errors:
                raise OutlineValidationError(
                    "Validation failed with no error details",
                    model=model.__name__,
                ) from e

            # Extract first error details
            first_error = errors[0]
            field = ".".join(str(loc) for loc in first_error.get("loc", ()))
            message = first_error.get("msg", "Validation failed")

            # Log multiple errors if present
            if len(errors) > 1:
                error_count = len(errors)
                _log_if_enabled(
                    logging.WARNING,
                    f"Multiple validation errors for {model.__name__}: "
                    f"{error_count} error(s)",
                )

                # Log details with limit
                _log_if_enabled(logging.DEBUG, "Validation error details:")
                logged_count = min(error_count, _MAX_LOGGED_ERRORS)
                for i, error in enumerate(errors[:logged_count], 1):
                    error_field = ".".join(str(loc) for loc in error.get("loc", ()))
                    error_msg = error.get("msg", "Unknown error")
                    _log_if_enabled(logging.DEBUG, f"  {i}. {error_field}: {error_msg}")

                if error_count > _MAX_LOGGED_ERRORS:
                    remaining = error_count - _MAX_LOGGED_ERRORS
                    _log_if_enabled(
                        logging.DEBUG, f"  ... and {remaining} more error(s)"
                    )

            raise OutlineValidationError(
                message,
                field=field,
                model=model.__name__,
            ) from e

        except Exception as e:
            # Catch any other unexpected errors during validation
            msg = f"Unexpected error during validation: {e}"
            _log_if_enabled(logging.ERROR, msg, exc_info=True)
            raise OutlineValidationError(
                msg,
                model=model.__name__,
            ) from e

    @staticmethod
    def parse_simple(data: dict[str, object]) -> bool:
        """Parse simple success responses.

        Handles various response formats:
        - {"success": true/false}
        - {"error": "..."}
        - {"message": "..."}
        - Empty dict (assumed success)

        :param data: Response data
        :return: True if successful
        """
        # Type validation
        if not isinstance(data, dict):
            _log_if_enabled(
                logging.WARNING,
                f"Expected dict in parse_simple, got {type(data).__name__}",
            )
            return False

        # Check explicit success field
        if "success" in data:
            success = data["success"]
            if not isinstance(success, bool):
                _log_if_enabled(
                    logging.WARNING,
                    f"success field is not bool: {type(success).__name__}, "
                    f"coercing to bool",
                )
                return bool(success)
            return success

        # Check for error indicators - return opposite of error presence
        return not ("error" in data or "message" in data)

    @staticmethod
    def validate_response_structure(
        data: dict[str, object],
        required_fields: Sequence[str] | None = None,
    ) -> bool:
        """Validate response structure without full parsing.

        Performs lightweight validation before expensive parsing.

        :param data: Response data
        :param required_fields: Sequence of required field names
        :return: True if structure is valid
        """
        # Type validation
        if not isinstance(data, dict):
            return False

        # Empty dict is valid if no required fields
        if not data and not required_fields:
            return True

        # Check required fields
        if required_fields:
            return all(field in data for field in required_fields)

        # No required fields = valid
        return True

    @staticmethod
    def extract_error_message(data: dict[str, object]) -> str | None:
        """Extract error message from response data.

        Checks common error field names in order of preference.

        :param data: Response data
        :return: Error message or None if not found
        """
        if not isinstance(data, dict):
            return None

        # Common error field names in order of preference
        error_fields = ("error", "message", "error_message", "msg")

        for field in error_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str):
                    return value
                # Convert non-string to string
                return str(value) if value is not None else None

        return None

    @staticmethod
    def is_error_response(data: dict[str, object]) -> bool:
        """Check if response indicates an error.

        :param data: Response data
        :return: True if response is an error
        """
        if not isinstance(data, dict):
            return False

        # Check for explicit error indicators
        if "error" in data or "error_message" in data:
            return True

        # Check success field
        if "success" in data:
            success = data["success"]
            return success is False

        return False


__all__ = [
    "JsonDict",
    "ResponseParser",
]
