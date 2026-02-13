from __future__ import annotations

import pytest

from pyoutlineapi.exceptions import (
    APIError,
    CircuitOpenError,
    ConfigurationError,
    OutlineConnectionError,
    OutlineError,
    OutlineTimeoutError,
    ValidationError,
    format_error_chain,
    get_retry_delay,
    get_safe_error_dict,
    is_retryable,
)

PLACEHOLDER_VALUE = "x"
UPDATED_VALUE = "changed"


def test_outline_error_sanitizes_and_truncates_message():
    message = "password=supersecret " + ("a" * 2000)
    err = OutlineError(message, safe_details={"field": "x"})
    text = str(err)
    assert "***PASSWORD***" in text
    assert "..." in text
    assert "field=x" in text


def test_outline_error_non_string_message_and_details_copy():
    err = OutlineError(
        123,
        details={"secret": PLACEHOLDER_VALUE},
        safe_details={"safe": "y"},
    )
    assert "123" in str(err)
    details = err.details
    details["secret"] = UPDATED_VALUE
    assert err.details["secret"] == PLACEHOLDER_VALUE
    safe = err.safe_details
    safe["safe"] = "changed"
    assert err.safe_details["safe"] == "y"


def test_outline_error_details_properties():
    err = OutlineError("oops")
    assert err.details == {}
    assert err.safe_details == {}


def test_outline_error_repr():
    err = OutlineError("oops")
    assert repr(err) == "OutlineError('oops')"


def test_api_error_properties_and_retryable():
    err = APIError("fail", status_code=503, endpoint="/server")
    assert err.is_retryable is True
    assert err.is_server_error is True
    assert err.is_client_error is False
    assert err.is_rate_limit_error is False

    err_no_status = APIError("fail")
    assert err_no_status.is_retryable is False


def test_circuit_open_error_validation_and_delay():
    err = CircuitOpenError("open", retry_after=12.3)
    assert err.is_retryable is True
    assert err.default_retry_delay == 12.3
    with pytest.raises(ValueError, match=r".*"):
        CircuitOpenError("open", retry_after=-1)


def test_configuration_and_validation_errors():
    config_err = ConfigurationError("bad", field="api_url", security_issue=True)
    assert config_err.safe_details["field"] == "api_url"
    assert config_err.safe_details["security_issue"] is True

    val_err = ValidationError("bad", field="port", model="Server")
    assert val_err.safe_details["field"] == "port"
    assert val_err.safe_details["model"] == "Server"

    config_err2 = ConfigurationError("bad", field="only")
    assert config_err2.safe_details["field"] == "only"
    val_err2 = ValidationError("bad", model="OnlyModel")
    assert val_err2.safe_details["model"] == "OnlyModel"

    config_err3 = ConfigurationError("bad", security_issue=True)
    assert config_err3.safe_details["security_issue"] is True

    val_err3 = ValidationError("bad", field="field-only")
    assert val_err3.safe_details["field"] == "field-only"


def test_connection_and_timeout_errors():
    conn_err = OutlineConnectionError("down", host="example.com", port=443)
    assert conn_err.is_retryable is True
    assert conn_err.safe_details["host"] == "example.com"
    assert conn_err.safe_details["port"] == 443

    conn_err2 = OutlineConnectionError("down")
    assert conn_err2.safe_details == {}

    conn_err3 = OutlineConnectionError("down", port=80)
    assert conn_err3.safe_details["port"] == 80

    timeout_err = OutlineTimeoutError("slow", timeout=1.23, operation="get")
    assert timeout_err.is_retryable is True
    assert timeout_err.safe_details["timeout"] == 1.23
    assert timeout_err.safe_details["operation"] == "get"

    timeout_err2 = OutlineTimeoutError("slow")
    assert timeout_err2.safe_details == {}

    timeout_err3 = OutlineTimeoutError("slow", operation="op")
    assert timeout_err3.safe_details["operation"] == "op"


def test_retry_helpers_and_safe_error_dict():
    api_err = APIError("fail", status_code=400)
    assert is_retryable(api_err) is False
    assert get_retry_delay(api_err) is None

    not_outline = ValueError("x")
    assert is_retryable(not_outline) is False
    assert get_retry_delay(not_outline) is None

    data = get_safe_error_dict(api_err)
    assert data["type"] == "APIError"
    assert data["status_code"] == 400
    assert data["is_client_error"] is True

    data2 = get_safe_error_dict(APIError("fail"))
    assert "is_client_error" not in data2
    assert "is_server_error" not in data2

    data3 = get_safe_error_dict(OutlineConnectionError("down", host="h", port=1))
    assert data3["host"] == "h"
    assert data3["port"] == 1

    timeout_err = OutlineTimeoutError("slow")
    assert get_retry_delay(timeout_err) == timeout_err.default_retry_delay

    circuit_err = CircuitOpenError("open", retry_after=5.0)
    data4 = get_safe_error_dict(circuit_err)
    assert data4["retry_after"] == 5.0

    config_err = ConfigurationError("bad", security_issue=False)
    data5 = get_safe_error_dict(config_err)
    assert data5["security_issue"] is False

    validation_err = ValidationError("bad")
    data6 = get_safe_error_dict(validation_err)
    assert "field" not in data6

    data7 = get_safe_error_dict(OutlineTimeoutError("slow", timeout=2.0))
    assert data7["timeout"] == 2.0


def test_format_error_chain_uses_cause_or_context():
    try:
        try:
            raise KeyError("root")
        except KeyError as err:
            raise ValueError("child") from err
    except Exception as exc:
        chain = format_error_chain(exc)
    assert len(chain) == 2
