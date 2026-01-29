from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel

from pyoutlineapi.exceptions import ValidationError as OutlineValidationError
from pyoutlineapi.response_parser import ResponseParser


class SimpleModel(BaseModel):
    id: int
    name: str


def test_parse_non_dict_raises_validation_error():
    with pytest.raises(OutlineValidationError) as exc:
        ResponseParser.parse(["bad"], SimpleModel)  # type: ignore[arg-type]
    assert exc.value.safe_details["model"] == "SimpleModel"


def test_parse_as_json_returns_dict():
    data = {"id": 1, "name": "test"}
    result = ResponseParser.parse(data, SimpleModel, as_json=True)
    assert result["id"] == 1
    assert result["name"] == "test"


def test_parse_invalid_data_logs_and_raises(caplog):
    data = {"id": "bad"}  # missing name and wrong id type
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.response_parser"):
        with pytest.raises(OutlineValidationError) as exc:
            ResponseParser.parse(data, SimpleModel, as_json=False)
    assert exc.value.safe_details["model"] == "SimpleModel"


def test_parse_unexpected_exception():
    class BadModel(SimpleModel):
        @classmethod
        def model_validate(cls, data):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    with pytest.raises(OutlineValidationError) as exc:
        ResponseParser.parse({"id": 1, "name": "x"}, BadModel)
    assert "Unexpected error during validation" in str(exc.value)


def test_parse_simple_variants(caplog):
    assert ResponseParser.parse_simple({"success": True}) is True
    assert ResponseParser.parse_simple({"success": False}) is False

    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.response_parser"):
        assert ResponseParser.parse_simple({"success": "yes"}) is True
    assert ResponseParser.parse_simple({"error": "fail"}) is False
    assert ResponseParser.parse_simple({"message": "fail"}) is False
    assert ResponseParser.parse_simple({}) is True
    assert ResponseParser.parse_simple(["bad"]) is False  # type: ignore[arg-type]


def test_validate_response_structure():
    assert ResponseParser.validate_response_structure({"id": 1}, ["id"]) is True
    assert ResponseParser.validate_response_structure({"id": 1}, ["id", "name"]) is False
    assert ResponseParser.validate_response_structure({}, None) is True
    assert ResponseParser.validate_response_structure(["bad"], ["id"]) is False  # type: ignore[arg-type]


def test_extract_error_message_and_is_error_response():
    assert ResponseParser.extract_error_message({"error": 1}) == "1"
    assert ResponseParser.extract_error_message({"message": None}) is None
    assert ResponseParser.extract_error_message({"success": True}) is None

    assert ResponseParser.is_error_response({"error_message": "bad"}) is True
    assert ResponseParser.is_error_response({"success": False}) is True
    assert ResponseParser.is_error_response({"success": True}) is False
    assert ResponseParser.is_error_response({}) is False
    assert ResponseParser.is_error_response(["bad"]) is False  # type: ignore[arg-type]
