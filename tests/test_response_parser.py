from __future__ import annotations

import logging
from typing import Any, cast

import pytest
from pydantic import BaseModel, ValidationError

from pyoutlineapi.common_types import JsonValue
from pyoutlineapi.exceptions import ValidationError as OutlineValidationError
from pyoutlineapi.response_parser import ResponseParser


class SimpleModel(BaseModel):
    id: int
    name: str


class MultiErrorModel(BaseModel):
    a: int
    b: int


def test_parse_non_dict_raises_validation_error():
    bad_data = cast(dict[str, JsonValue], ["bad"])
    with pytest.raises(OutlineValidationError) as exc:
        ResponseParser.parse(bad_data, SimpleModel)
    assert exc.value.safe_details["model"] == "SimpleModel"


def test_parse_as_json_returns_dict():
    data: dict[str, JsonValue] = {"id": 1, "name": "test"}
    result = ResponseParser.parse(data, SimpleModel, as_json=True)
    assert result["id"] == 1
    assert result["name"] == "test"


def test_parse_invalid_data_logs_and_raises(caplog):
    data: dict[str, JsonValue] = {"id": "bad"}  # missing name and wrong id type
    with caplog.at_level(
        logging.WARNING,
        logger="pyoutlineapi.response_parser",
    ), pytest.raises(OutlineValidationError) as exc:
        ResponseParser.parse(data, SimpleModel, as_json=False)
    assert exc.value.safe_details["model"] == "SimpleModel"


def test_parse_empty_dict_debug_log(caplog):
    with caplog.at_level(
        logging.DEBUG,
        logger="pyoutlineapi.response_parser",
    ), pytest.raises(OutlineValidationError):
        ResponseParser.parse({}, SimpleModel)
    assert any("Parsing empty dict" in r.message for r in caplog.records)


def test_parse_validation_error_without_details():
    class EmptyErrorsModel(SimpleModel):
        @classmethod
        def model_validate(cls, obj: Any, **kwargs: Any) -> EmptyErrorsModel:
            raise ValidationError.from_exception_data("EmptyErrorsModel", [])

    with pytest.raises(OutlineValidationError) as exc:
        ResponseParser.parse({"id": 1, "name": "x"}, EmptyErrorsModel)
    assert "no error details" in str(exc.value)


def test_parse_validation_error_many_details(caplog):
    logger = logging.getLogger("pyoutlineapi.response_parser")
    logger.setLevel(logging.DEBUG)

    class ManyErrorsModel(SimpleModel):
        @classmethod
        def model_validate(cls, obj: Any, **kwargs: Any) -> ManyErrorsModel:
            errors = [
                {
                    "type": "value_error",
                    "loc": ("field", idx),
                    "msg": "bad",
                    "input": obj,
                    "ctx": {"error": "boom"},
                }
                for idx in range(11)
            ]
            raise ValidationError.from_exception_data(
                "ManyErrorsModel",
                errors,  # type: ignore[arg-type]  # synthetic pydantic error details for test
            )

    with caplog.at_level(
        logging.DEBUG,
        logger="pyoutlineapi.response_parser",
    ), pytest.raises(OutlineValidationError):
        ResponseParser.parse({"id": 1, "name": "x"}, ManyErrorsModel)
    assert any("Validation error details" in r.message for r in caplog.records)
    assert any("more error(s)" in r.message for r in caplog.records)


def test_parse_validation_error_multiple_fields(caplog):
    logger = logging.getLogger("pyoutlineapi.response_parser")
    logger.setLevel(logging.DEBUG)
    with caplog.at_level(
        logging.DEBUG,
        logger="pyoutlineapi.response_parser",
    ), pytest.raises(OutlineValidationError):
        ResponseParser.parse({}, MultiErrorModel)
    assert any("Multiple validation errors" in r.message for r in caplog.records)


def test_parse_validation_error_multiple_fields_without_logging():
    logger = logging.getLogger("pyoutlineapi.response_parser")
    logger.setLevel(logging.ERROR)
    with pytest.raises(OutlineValidationError):
        ResponseParser.parse({}, MultiErrorModel)


def test_parse_unexpected_exception():
    class BadModel(SimpleModel):
        @classmethod
        def model_validate(cls, obj: Any, **kwargs: Any) -> BadModel:
            raise RuntimeError("boom")

    with pytest.raises(OutlineValidationError) as exc:
        ResponseParser.parse({"id": 1, "name": "x"}, BadModel)
    assert "Unexpected error during validation" in str(exc.value)


def test_parse_unexpected_exception_logs_error(caplog):
    logger = logging.getLogger("pyoutlineapi.response_parser")
    logger.setLevel(logging.ERROR)

    class BadModel(SimpleModel):
        @classmethod
        def model_validate(cls, obj: Any, **kwargs: Any) -> BadModel:
            raise RuntimeError("boom")

    with caplog.at_level(
        logging.ERROR,
        logger="pyoutlineapi.response_parser",
    ), pytest.raises(OutlineValidationError):
        ResponseParser.parse({"id": 1, "name": "x"}, BadModel)
    assert any(
        "Unexpected error during validation" in r.message for r in caplog.records
    )


def test_parse_simple_variants(caplog):
    logger = logging.getLogger("pyoutlineapi.response_parser")
    logger.setLevel(logging.WARNING)
    assert ResponseParser.parse_simple({"success": True}) is True
    assert ResponseParser.parse_simple({"success": False}) is False

    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.response_parser"):
        assert ResponseParser.parse_simple({"success": "yes"}) is True
    assert any("success field is not bool" in r.message for r in caplog.records)
    assert ResponseParser.parse_simple({"error": "fail"}) is False
    assert ResponseParser.parse_simple({"message": "fail"}) is False
    assert ResponseParser.parse_simple({}) is True
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.response_parser"):
        assert ResponseParser.parse_simple(["bad"]) is False
    assert any("Expected dict in parse_simple" in r.message for r in caplog.records)


def test_parse_simple_logs_warning_for_non_dict(caplog):
    logger = logging.getLogger("pyoutlineapi.response_parser")
    logger.setLevel(logging.WARNING)
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.response_parser"):
        assert ResponseParser.parse_simple(123) is False
    assert any("Expected dict in parse_simple" in r.message for r in caplog.records)


def test_parse_simple_no_warning_when_logger_disabled():
    logger = logging.getLogger("pyoutlineapi.response_parser")
    logger.setLevel(logging.ERROR)
    assert ResponseParser.parse_simple(123) is False


def test_validate_response_structure():
    assert ResponseParser.validate_response_structure({"id": 1}, ["id"]) is True
    assert (
        ResponseParser.validate_response_structure({"id": 1}, ["id", "name"]) is False
    )
    assert ResponseParser.validate_response_structure({}, None) is True
    assert ResponseParser.validate_response_structure({"id": 1}, []) is True
    assert ResponseParser.validate_response_structure(["bad"], ["id"]) is False


def test_extract_error_message_and_is_error_response():
    assert ResponseParser.extract_error_message({"error": 1}) == "1"
    assert ResponseParser.extract_error_message({"message": None}) is None
    assert ResponseParser.extract_error_message({"msg": "oops"}) == "oops"
    assert ResponseParser.extract_error_message({"success": True}) is None
    assert ResponseParser.extract_error_message(["bad"]) is None

    assert ResponseParser.is_error_response({"error_message": "bad"}) is True
    assert ResponseParser.is_error_response({"success": False}) is True
    assert ResponseParser.is_error_response({"success": True}) is False
    assert ResponseParser.is_error_response({}) is False
    assert ResponseParser.is_error_response(["bad"]) is False
