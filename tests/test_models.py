from __future__ import annotations

import pytest

from pyoutlineapi.models import (
    AccessKey,
    AccessKeyList,
    DataLimit,
    DataLimitRequest,
    ErrorResponse,
    ExperimentalMetrics,
    HealthCheckResult,
    Server,
    ServerMetrics,
    ServerSummary,
    TunnelTime,
)


def test_data_limit_conversions():
    limit = DataLimit.from_megabytes(1)
    assert limit.bytes == 1024 * 1024
    assert DataLimit.from_kilobytes(1).kilobytes == 1
    assert DataLimit.from_gigabytes(1).gigabytes == 1
    assert limit.megabytes == 1


def test_access_key_properties():
    key = AccessKey(
        id="key-1",
        name=None,
        password="pwd",
        port=12345,
        method="aes-256-gcm",
        accessUrl="ss://example",
        dataLimit=None,
    )
    assert key.display_name == "Key-key-1"
    assert key.has_data_limit is False


def test_access_key_list():
    key = AccessKey(
        id="key-1",
        name="Name",
        password="pwd",
        port=12345,
        method="aes-256-gcm",
        accessUrl="ss://example",
        dataLimit=None,
    )
    lst = AccessKeyList(accessKeys=[key])
    assert lst.count == 1
    assert lst.is_empty is False
    assert lst.get_by_id("key-1") is not None
    assert lst.get_by_id("missing") is None
    assert lst.get_by_name("Name") == [key]
    assert lst.filter_without_limits() == [key]
    assert lst.filter_with_limits() == []


def test_server_and_metrics():
    server = Server(
        name="Server",
        serverId="srv",
        metricsEnabled=True,
        createdTimestampMs=1000,
        portForNewAccessKeys=12345,
        hostnameForAccessKeys="host",
        accessKeyDataLimit=None,
        version="1.0",
    )
    assert server.has_global_limit is False
    assert server.created_timestamp_seconds == 1.0

    metrics = ServerMetrics(bytesTransferredByUserId={"u": 100, "v": 200})
    assert metrics.total_bytes == 300
    assert metrics.user_count == 2
    assert metrics.total_gigabytes > 0
    assert metrics.get_user_bytes("u") == 100
    assert metrics.get_user_bytes("missing") == 0
    assert metrics.top_users(limit=1)[0][0] in {"u", "v"}


def test_server_name_validation_error():
    with pytest.raises(ValueError):
        Server(
            name="",
            serverId="srv",
            metricsEnabled=True,
            createdTimestampMs=1000,
            portForNewAccessKeys=12345,
        )


def test_server_name_validation_none(monkeypatch):
    from pyoutlineapi import common_types

    def fake_validate_name(_v):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(common_types.Validators, "validate_name", fake_validate_name)
    with pytest.raises(ValueError):
        Server(
            name="Server",
            serverId="srv",
            metricsEnabled=True,
            createdTimestampMs=1000,
            portForNewAccessKeys=12345,
        )


def test_experimental_metrics_lookup(experimental_metrics_dict):
    metrics = ExperimentalMetrics(**experimental_metrics_dict)
    assert metrics.get_key_metric("key-1") is not None
    assert metrics.get_key_metric("missing") is None


def test_health_check_result_and_summary():
    result = HealthCheckResult(
        healthy=True,
        timestamp=1.0,
        checks={"c1": {"status": "healthy"}, "c2": {"status": "unhealthy"}},
    )
    assert result.failed_checks == ["c2"]
    assert result.success_rate == 0.5

    summary = ServerSummary(
        server={"id": "s"},
        access_keys_count=1,
        healthy=True,
        transfer_metrics={"a": 10, "b": 20},
    )
    assert summary.total_bytes_transferred == 30
    assert summary.total_gigabytes_transferred > 0
    assert summary.has_errors is False

    empty_summary = ServerSummary(
        server={"id": "s"},
        access_keys_count=0,
        healthy=False,
        transfer_metrics=None,
        error="fail",
    )
    assert empty_summary.total_bytes_transferred == 0
    assert empty_summary.has_errors is True


def test_error_response_and_requests():
    err = ErrorResponse(code="x", message="oops")
    assert str(err) == "x: oops"

    payload = DataLimitRequest(limit=DataLimit(bytes=123)).to_payload()
    assert payload == {"limit": {"bytes": 123}}

    time = TunnelTime(seconds=120)
    assert time.minutes == 2
    assert time.hours == 2 / 60


def test_health_check_result_success_rate_empty():
    result = HealthCheckResult(healthy=True, timestamp=1.0, checks={})
    assert result.success_rate == 1.0
