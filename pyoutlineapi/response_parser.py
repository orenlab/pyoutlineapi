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

import logging
from typing import Any, TypeVar, Union, overload, Literal

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

# Type aliases
JsonDict = dict[str, Any]
ResponseType = Union[JsonDict, BaseModel]
T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class ResponseParser:
    """Utility class for parsing API responses with enhanced error handling."""

    @staticmethod
    @overload
    async def parse_response_data(
            data: dict[str, Any],
            model: type[T],
            json_format: Literal[True],
    ) -> JsonDict:
        ...

    @staticmethod
    @overload
    async def parse_response_data(
            data: dict[str, Any],
            model: type[T],
            json_format: Literal[False],
    ) -> T:
        ...

    @staticmethod
    @overload
    async def parse_response_data(
            data: dict[str, Any],
            model: type[T],
            json_format: bool,
    ) -> ResponseType:
        ...

    @staticmethod
    async def parse_response_data(
            data: dict[str, Any],
            model: type[T],
            json_format: bool = False,
    ) -> ResponseType:
        """
        Parse and validate response data with enhanced error handling.

        Args:
            data: Response data to parse
            model: Pydantic model for validation
            json_format: Whether to return raw JSON

        Returns:
            Validated response data

        Raises:
            ValueError: If response validation fails with detailed error info
        """
        try:
            # Handle simple success responses
            if data.get("success") is True and not json_format:
                return model(success=True) if hasattr(model, "success") else data

            # Attempt validation
            validated = model.model_validate(data)
            return validated.model_dump(by_alias=True) if json_format else validated

        except ValidationError as e:
            error_details = ResponseParser._format_validation_error(e, data, model)
            logger.error(f"Response validation failed: {error_details}")
            raise ValueError(f"Response validation error: {error_details}") from e
        except Exception as e:
            logger.error(f"Unexpected error during response parsing: {e}")
            raise ValueError(f"Response parsing error: {e}") from e

    @staticmethod
    def _format_validation_error(
            validation_error: ValidationError,
            data: dict[str, Any],
            model: type[BaseModel],
    ) -> str:
        """Format validation error with helpful context."""
        errors = validation_error.errors()

        if not errors:
            return "Unknown validation error"

        # Get the first error for the main message
        first_error = errors[0]
        field_path = " -> ".join(str(loc) for loc in first_error.get("loc", []))
        error_msg = first_error.get("msg", "Unknown error")
        error_type = first_error.get("type", "unknown")
        input_value = first_error.get("input", "unknown")

        # Build detailed error message
        details = [
            f"Model: {model.__name__}",
            f"Field: {field_path}",
            f"Error: {error_msg}",
            f"Type: {error_type}",
            f"Input: {input_value}",
        ]

        # Add suggestions based on common error patterns
        suggestions = ResponseParser._get_error_suggestions(first_error, data)
        if suggestions:
            details.extend(["", "Suggestions:"] + suggestions)

        # Add context about the response data
        if len(str(data)) < 500:  # Only show if data is not too large
            details.extend(["", f"Response data: {data}"])
        else:
            details.append(f"Response data size: {len(str(data))} characters")

        return "\n".join(f"  {detail}" for detail in details)

    @staticmethod
    def _get_error_suggestions(error: ErrorDetails, data: dict[str, Any]) -> list[str]:
        """Generate helpful suggestions based on the error type."""
        suggestions = []
        error_type = error.get("type", "")
        field_path = error.get("loc", [])
        input_value = error.get("input")

        match error_type:
            case "value_error" if "empty" in str(error.get("msg", "")).lower():
                if any("name" in str(loc) for loc in field_path):
                    suggestions.extend(
                        [
                            "• API returned an empty name field",
                            "• This is normal for unnamed access keys",
                            "• Consider updating the model to handle empty names as None",
                        ]
                    )
                else:
                    suggestions.append("• Check if the field should allow empty values")

            case "missing":
                suggestions.extend(
                    [
                        f"• Field '{'.'.join(str(loc) for loc in field_path)}' is required but missing",
                        "• Check if the API response structure has changed",
                        "• Verify the API endpoint is correct",
                    ]
                )

            case "string_type":
                suggestions.extend(
                    [
                        f"• Expected string but got {type(input_value).__name__}: {input_value}",
                        "• Check if the API response format has changed",
                    ]
                )

            case "int_parsing" | "int_type":
                suggestions.extend(
                    [
                        f"• Expected integer but got: {input_value}",
                        "• Check if the value should be converted or if the API changed",
                    ]
                )

            case "url_parsing":
                suggestions.extend(
                    [
                        f"• Invalid URL format: {input_value}",
                        "• Check if the URL structure from the API is correct",
                    ]
                )

            case _:
                if any("port" in str(loc) for loc in field_path):
                    suggestions.extend(
                        [
                            "• Port values must be between 1025-65535",
                            "• Check if the port value from the API is valid",
                        ]
                    )
                elif any("bytes" in str(loc) for loc in field_path):
                    suggestions.extend(
                        [
                            "• Byte values must be non-negative integers",
                            "• Check if the data limit value is correct",
                        ]
                    )

        # Add generic suggestions if no specific ones were added
        if not suggestions:
            suggestions.extend(
                [
                    "• Verify the API response format matches the expected model",
                    "• Check if the API version or endpoint has changed",
                    "• Consider using json_format=True to see raw response data",
                ]
            )

        return suggestions

    @staticmethod
    def parse_simple_response_data(
            data: dict[str, Any], json_format: bool = False
    ) -> Union[bool, JsonDict]:
        """
        Parse simple responses that don't need model validation.

        Args:
            data: Response data
            json_format: Whether to return JSON format

        Returns:
            True for success or JSON response
        """
        if data.get("success"):
            return data if json_format else True

        # For other responses, assume success if no error
        return data if json_format else True

    @staticmethod
    async def safe_parse_response_data(
            data: dict[str, Any],
            model: type[T],
            json_format: bool = False,
            fallback_to_json: bool = True,
    ) -> Union[T, JsonDict]:
        """
        Safely parse response data with fallback to raw JSON on validation errors.

        This method is useful when you want to handle validation errors gracefully
        and still get the data, even if it doesn't match the expected model.

        Args:
            data: Response data to parse
            model: Pydantic model for validation
            json_format: Whether to return raw JSON
            fallback_to_json: If True, return raw JSON on validation errors

        Returns:
            Validated response data or raw JSON if validation fails
        """
        try:
            return await ResponseParser.parse_response_data(data, model, json_format)
        except ValueError as e:
            if fallback_to_json:
                logger.warning(f"Validation failed, returning raw JSON: {e}")
                return data
            raise
        except Exception as e:
            logger.error(f"Unexpected error in safe_parse_response_data: {e}")
            if fallback_to_json:
                return data
            raise
