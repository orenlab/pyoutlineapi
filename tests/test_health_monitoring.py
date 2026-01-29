from __future__ import annotations

import pytest

from pyoutlineapi.health_monitoring import (
    HealthCheckHelper,
    HealthMonitor,
    HealthStatus,
    PerformanceMetrics,
)


class DummyClient:
    async def get_server_info(self):
        return {"name": "ok"}

    def get_circuit_metrics(self):
        return None


@pytest.mark.asyncio
async def test_health_monitor_check_and_cache():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)
    result = await monitor.check()
    assert result.healthy is True
    cached = await monitor.check()
    assert cached is result


@pytest.mark.asyncio
async def test_health_monitor_quick_check():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)
    assert await monitor.quick_check() is True


def test_health_monitor_invalid_cache_ttl():
    with pytest.raises(ValueError):
        HealthMonitor(DummyClient(), cache_ttl=0.0)


class CircuitClient(DummyClient):
    def get_circuit_metrics(self):
        return {"state": "OPEN", "success_rate": 0.2}


@pytest.mark.asyncio
async def test_health_monitor_custom_check_and_circuit():
    monitor = HealthMonitor(CircuitClient(), cache_ttl=1.0)

    async def custom_check(_client):  # type: ignore[no-untyped-def]
        return {"status": "ok"}

    monitor.add_custom_check("custom", custom_check)
    result = await monitor.check(use_cache=False)
    assert "custom" in result.checks
    assert result.healthy is False
    assert monitor.remove_custom_check("custom") is True
    assert monitor.remove_custom_check("missing") is False
    assert monitor.clear_custom_checks() == 0


def test_health_status_properties():
    status = HealthStatus(
        healthy=False,
        timestamp=1.0,
        checks={
            "c1": {"status": "healthy"},
            "c2": {"status": "warning"},
            "c3": {"status": "degraded"},
            "c4": {"status": "unhealthy"},
        },
        metrics={},
    )
    assert status.failed_checks == ["c4"]
    assert status.warning_checks == ["c2"]
    assert status.total_checks == 4
    assert status.passed_checks == 1
    assert status.is_degraded is True
    data = status.to_dict()
    assert data["failed_checks"] == ["c4"]


@pytest.mark.asyncio
async def test_wait_until_healthy_timeout(monkeypatch):
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)

    async def always_false():  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr(HealthMonitor, "quick_check", always_false)
    result = await monitor.wait_for_healthy(timeout=0.01, check_interval=0.005)
    assert result is False


class FailingClient(DummyClient):
    async def get_server_info(self):
        raise RuntimeError("fail")


@pytest.mark.asyncio
async def test_health_monitor_failure_path():
    monitor = HealthMonitor(FailingClient(), cache_ttl=1.0)
    result = await monitor.check(use_cache=False)
    assert result.healthy is False


@pytest.mark.asyncio
async def test_custom_check_error_path():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)

    async def bad_check(_client):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monitor.add_custom_check("bad", bad_check)
    result = await monitor.check(use_cache=False)
    assert result.checks["bad"]["status"] == "error"


@pytest.mark.asyncio
async def test_quick_check_exception_path():
    monitor = HealthMonitor(FailingClient(), cache_ttl=1.0)
    assert await monitor.quick_check() is False


def test_record_request_and_metrics():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)
    monitor.record_request(True, 1.0)
    monitor.record_request(False, 2.0)
    metrics = monitor.get_metrics()
    assert metrics["total_requests"] == 2
    monitor.reset_metrics()
    assert monitor.get_metrics()["total_requests"] == 0

    with pytest.raises(ValueError):
        monitor.record_request(True, -1.0)


def test_performance_metrics_and_helper():
    metrics = PerformanceMetrics()
    assert metrics.success_rate == 1.0
    metrics.total_requests = 10
    metrics.successful_requests = 7
    assert metrics.failure_rate == pytest.approx(0.3)

    helper = HealthCheckHelper()
    assert helper.determine_status_by_time(0.1) in {"healthy", "warning", "degraded"}
    assert helper.determine_status_by_time(10.0) == "degraded"
    assert helper.determine_circuit_status("OPEN", 0.1) == "unhealthy"
    assert helper.determine_circuit_status("HALF_OPEN", 0.1) == "warning"
    assert helper.determine_circuit_status("CLOSED", 0.8) in {
        "warning",
        "degraded",
        "healthy",
    }
    assert helper.determine_performance_status(0.1, 10.0) == "unhealthy"
    assert helper.determine_performance_status(0.95, 0.5) == "warning"


@pytest.mark.asyncio
async def test_cache_valid_and_quick_check_cached(monkeypatch):
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)

    async def fake_check(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    result = await monitor.check(use_cache=False)
    assert monitor.cache_valid is True

    monkeypatch.setattr(DummyClient, "get_server_info", fake_check)
    assert await monitor.quick_check() is True


@pytest.mark.asyncio
async def test_quick_check_cached_result():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)
    monitor._cached_result = HealthStatus(
        healthy=True, timestamp=1.0, checks={}, metrics={}
    )
    monitor._last_check_time = 0.0
    assert await monitor.quick_check() is True


@pytest.mark.asyncio
async def test_circuit_metrics_invalid_success_rate():
    class BadCircuitClient(DummyClient):
        def get_circuit_metrics(self):
            return {"state": "CLOSED", "success_rate": "bad"}

    monitor = HealthMonitor(BadCircuitClient(), cache_ttl=1.0)
    result = await monitor.check(use_cache=False)
    assert result.checks["circuit_breaker"]["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_custom_check_unhealthy_sets_overall():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)

    async def unhealthy_check(_client):  # type: ignore[no-untyped-def]
        return {"status": "unhealthy"}

    monitor.add_custom_check("unhealthy", unhealthy_check)
    result = await monitor.check(use_cache=False)
    assert result.healthy is False


def test_add_custom_check_validation_and_invalidate_cache():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)
    with pytest.raises(ValueError):
        monitor.add_custom_check("", lambda _c: None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        monitor.add_custom_check("x", "bad")  # type: ignore[arg-type]

    monitor._cached_result = HealthStatus(
        healthy=True, timestamp=1.0, checks={}, metrics={}
    )
    monitor.invalidate_cache()
    assert monitor.cache_valid is False
    assert monitor.custom_checks_count == 0


@pytest.mark.asyncio
async def test_wait_for_healthy_validation_errors():
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)
    with pytest.raises(ValueError):
        await monitor.wait_for_healthy(timeout=0.0, check_interval=1.0)
    with pytest.raises(ValueError):
        await monitor.wait_for_healthy(timeout=1.0, check_interval=0.0)


@pytest.mark.asyncio
async def test_wait_for_healthy_exception_in_check(monkeypatch):
    monitor = HealthMonitor(DummyClient(), cache_ttl=1.0)

    async def boom():  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(HealthMonitor, "quick_check", boom)
    result = await monitor.wait_for_healthy(timeout=0.01, check_interval=0.005)
    assert result is False
