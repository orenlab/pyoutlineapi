import asyncio
import logging

import pytest

from pyoutlineapi.audit import DefaultAuditLogger
from pyoutlineapi.exceptions import (
    APIError,
    CircuitOpenError,
    ConfigurationError,
    OutlineConnectionError,
    OutlineTimeoutError,
    ValidationError,
    get_safe_error_dict,
)

# ===== Exceptions Coverage =====


def test_get_safe_error_dict_all_variants():
    """Cover all branches in get_safe_error_dict."""

    # 1. APIError with all fields
    err1 = APIError("msg", status_code=400, endpoint="/test", response_data={"a": 1})
    d1 = get_safe_error_dict(err1)
    assert d1["status_code"] == 400
    assert d1["is_client_error"] is True

    # 2. APIError without status_code
    err2 = APIError("msg")
    d2 = get_safe_error_dict(err2)
    assert d2["status_code"] is None
    assert "is_client_error" not in d2

    # 3. CircuitOpenError
    err3 = CircuitOpenError("msg", retry_after=10.0)
    d3 = get_safe_error_dict(err3)
    assert d3["retry_after"] == 10.0

    # 4. ConfigurationError with all fields
    err4 = ConfigurationError("msg", field="api_url", security_issue=True)
    d4 = get_safe_error_dict(err4)
    assert d4["field"] == "api_url"
    assert d4["security_issue"] is True

    # 5. ConfigurationError minimal
    err5 = ConfigurationError("msg")
    d5 = get_safe_error_dict(err5)
    assert "field" not in d5
    assert d5["security_issue"] is False

    # 6. ValidationError with all fields
    err6 = ValidationError("msg", field="port", model="Server")
    d6 = get_safe_error_dict(err6)
    assert d6["field"] == "port"
    assert d6["model"] == "Server"

    # 7. ValidationError minimal
    err7 = ValidationError("msg")
    d7 = get_safe_error_dict(err7)
    assert "field" not in d7

    # 8. OutlineConnectionError with all fields
    err8 = OutlineConnectionError("msg", host="1.1.1.1", port=80)
    d8 = get_safe_error_dict(err8)
    assert d8["host"] == "1.1.1.1"
    assert d8["port"] == 80

    # 9. OutlineConnectionError minimal
    err9 = OutlineConnectionError("msg")
    d9 = get_safe_error_dict(err9)
    assert "host" not in d9

    # 10. OutlineTimeoutError with all fields
    err10 = OutlineTimeoutError("msg", timeout=5.0, operation="op")
    d10 = get_safe_error_dict(err10)
    assert d10["timeout"] == 5.0
    assert d10["operation"] == "op"

    # 11. OutlineTimeoutError minimal
    err11 = OutlineTimeoutError("msg")
    d11 = get_safe_error_dict(err11)
    assert "timeout" not in d11


# ===== Audit Coverage =====


@pytest.mark.asyncio
async def test_audit_logger_queue_full_coverage(caplog):
    """Cover the queue full branch in alog_action."""
    logger = DefaultAuditLogger(queue_size=1)

    # Fill the queue
    await logger._queue.put({"test": 1})

    # Force full exception triggering by not consuming
    # Specify logger name explicitly to ensure capture
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.audit"):
        await logger.alog_action("action", "resource")

    assert "Queue full" in caplog.text
    await logger.shutdown()


@pytest.mark.asyncio
async def test_audit_logger_shutdown_timeout_branches(caplog):
    """Cover queue drain timeout logic."""
    logger = DefaultAuditLogger()

    # Start processor
    await logger.alog_action("test", "res")

    # Mock queue join to timeout
    async def mock_join():
        # Wait a bit to simulate work
        await asyncio.sleep(0.01)
        # Raise timeout to trigger the warning
        raise asyncio.TimeoutError()

    logger._queue.join = mock_join  # type: ignore

    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.audit"):
        # Use a very short timeout for the shutdown call
        await logger.shutdown(timeout=0.001)

    assert "Queue did not drain" in caplog.text
