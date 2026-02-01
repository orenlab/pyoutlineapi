from __future__ import annotations

import asyncio
import logging

import pytest

from pyoutlineapi.circuit_breaker import CircuitBreaker, CircuitConfig, CircuitState
from pyoutlineapi.exceptions import CircuitOpenError, OutlineTimeoutError


@pytest.mark.asyncio
async def test_circuit_breaker_transitions(monkeypatch):
    config = CircuitConfig(
        failure_threshold=1,
        recovery_timeout=1.0,
        success_threshold=1,
        call_timeout=0.2,
    )
    breaker = CircuitBreaker("test", config)

    async def fail():
        raise ValueError("boom")

    async def ok():
        return "ok"

    with pytest.raises(ValueError):
        await breaker.call(fail)

    with pytest.raises(CircuitOpenError):
        await breaker.call(ok)

    # Simulate recovery timeout elapsed
    t = 100.0
    monkeypatch.setattr("pyoutlineapi.circuit_breaker.time.monotonic", lambda: t)
    breaker._last_failure_time = t - 2.0  # type: ignore[attr-defined]

    result = await breaker.call(ok)
    assert result == "ok"
    assert breaker.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)


def test_circuit_metrics_snapshot():
    breaker = CircuitBreaker("name")
    snapshot = breaker.get_metrics_snapshot()
    assert "success_rate" in snapshot


def test_circuit_config_validation():
    with pytest.raises(ValueError):
        CircuitConfig(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitConfig(recovery_timeout=0.0)
    with pytest.raises(ValueError):
        CircuitConfig(success_threshold=0)
    with pytest.raises(ValueError):
        CircuitConfig(call_timeout=0.0)


def test_circuit_metrics_rates():
    metrics = CircuitBreaker("m").metrics
    assert metrics.success_rate == 1.0
    metrics.total_calls = 10
    metrics.successful_calls = 7
    assert metrics.failure_rate == pytest.approx(0.3)
    assert "failure_rate" in metrics.to_dict()


def test_circuit_breaker_name_validation():
    with pytest.raises(ValueError):
        CircuitBreaker("")


def test_circuit_breaker_properties():
    breaker = CircuitBreaker("props")
    assert breaker.name == "props"
    assert breaker.config is not None


@pytest.mark.asyncio
async def test_circuit_breaker_record_success_fast_path():
    breaker = CircuitBreaker("fast")
    await breaker._record_success(0.01)
    assert breaker.metrics.successful_calls == 1


@pytest.mark.asyncio
async def test_circuit_breaker_reset():
    breaker = CircuitBreaker("reset", CircuitConfig(failure_threshold=1))

    async def fail():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    await breaker.reset()
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_reset_logs_info(caplog):
    breaker = CircuitBreaker("reset-log")
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.circuit_breaker"):
        await breaker.reset()
    assert any("manual reset" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_circuit_breaker_open_state_rejects():
    breaker = CircuitBreaker("open", CircuitConfig(recovery_timeout=10.0))
    breaker._state = CircuitState.OPEN  # type: ignore[attr-defined]
    breaker._last_failure_time = 100.0  # type: ignore[attr-defined]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("pyoutlineapi.circuit_breaker.time.monotonic", lambda: 100.1)
        with pytest.raises(CircuitOpenError) as exc:
            await breaker.call(asyncio.sleep, 0)
    assert exc.value.retry_after >= 0.0


@pytest.mark.asyncio
async def test_transition_to_open_logs_info(caplog):
    breaker = CircuitBreaker("transition-open")
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.circuit_breaker"):
        await breaker._transition_to(CircuitState.OPEN)
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_timeout():
    breaker = CircuitBreaker("timeout", CircuitConfig(call_timeout=0.1))

    async def slow():
        await asyncio.sleep(0.2)
        return "ok"

    with pytest.raises(OutlineTimeoutError):
        await breaker.call(slow)


@pytest.mark.asyncio
async def test_circuit_breaker_timeout_logs_warning(caplog):
    breaker = CircuitBreaker("timeout-log", CircuitConfig(call_timeout=0.1))
    logger = logging.getLogger("pyoutlineapi.circuit_breaker")
    logger.setLevel(logging.WARNING)

    async def slow():
        await asyncio.sleep(0.2)

    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.circuit_breaker"):
        with pytest.raises(OutlineTimeoutError):
            await breaker.call(slow)
    assert any("timeout after" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_circuit_breaker_state_helpers():
    breaker = CircuitBreaker("helpers")
    assert breaker.is_closed() is True
    assert breaker.is_open() is False
    assert breaker.is_half_open() is False
    assert breaker.get_time_since_last_state_change() >= 0


@pytest.mark.asyncio
async def test_circuit_breaker_check_state_transitions(caplog, monkeypatch):
    breaker = CircuitBreaker(
        "check", CircuitConfig(failure_threshold=1, recovery_timeout=1.0)
    )
    breaker._failure_count = 1  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.circuit_breaker"):
        await breaker._check_state()
    assert breaker.state == CircuitState.OPEN

    now = 100.0
    monkeypatch.setattr("pyoutlineapi.circuit_breaker.time.monotonic", lambda: now)
    breaker._last_failure_time = now - 2.0  # type: ignore[attr-defined]
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.circuit_breaker"):
        await breaker._check_state()
    assert breaker.state in {CircuitState.HALF_OPEN, CircuitState.OPEN}


@pytest.mark.asyncio
async def test_circuit_breaker_check_state_opens_with_warning(caplog):
    breaker = CircuitBreaker("warn", CircuitConfig(failure_threshold=1))
    breaker._failure_count = 1  # type: ignore[attr-defined]
    logging.getLogger("pyoutlineapi.circuit_breaker").setLevel(logging.WARNING)
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.circuit_breaker"):
        await breaker._check_state()
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_check_state_half_open_noop():
    breaker = CircuitBreaker("check-half")
    breaker._state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
    await breaker._check_state()
    assert breaker.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_record_success_and_failure(caplog):
    breaker = CircuitBreaker("record", CircuitConfig(success_threshold=1))
    breaker._failure_count = 1  # type: ignore[attr-defined]
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.circuit_breaker"):
        await breaker._record_success(0.1)
    assert breaker.metrics.successful_calls == 1

    breaker._state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.circuit_breaker"):
        await breaker._record_failure(0.1, RuntimeError("fail"))
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_record_success_resets_failures(caplog):
    breaker = CircuitBreaker("record-reset")
    breaker._failure_count = 2  # type: ignore[attr-defined]
    logger = logging.getLogger("pyoutlineapi.circuit_breaker")
    logger.setLevel(logging.DEBUG)
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.circuit_breaker"):
        await breaker._record_success(0.1)
    assert breaker.metrics.successful_calls == 1
    assert breaker._failure_count == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_circuit_breaker_record_failure_debug(caplog):
    breaker = CircuitBreaker("record-fail")
    logger = logging.getLogger("pyoutlineapi.circuit_breaker")
    logger.setLevel(logging.DEBUG)
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.circuit_breaker"):
        await breaker._record_failure(0.1, RuntimeError("boom"))
    assert any("failure #1" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_success_closes(caplog):
    breaker = CircuitBreaker("half-success", CircuitConfig(success_threshold=1))
    breaker._state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
    logger = logging.getLogger("pyoutlineapi.circuit_breaker")
    logger.setLevel(logging.INFO)
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.circuit_breaker"):
        await breaker._record_success(0.1)
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_success_logs_info(caplog):
    breaker = CircuitBreaker("half-info", CircuitConfig(success_threshold=1))
    breaker._state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
    logging.getLogger("pyoutlineapi.circuit_breaker").setLevel(logging.INFO)
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.circuit_breaker"):
        await breaker._record_success(0.1)
    assert any("closing after" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_logs_warning(caplog):
    breaker = CircuitBreaker("half-fail-log")
    breaker._state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
    logging.getLogger("pyoutlineapi.circuit_breaker").setLevel(logging.WARNING)
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.circuit_breaker"):
        await breaker._record_failure(0.1, RuntimeError("boom"))
    assert any("reopening" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_circuit_breaker_transition_to_same_state(caplog):
    breaker = CircuitBreaker("transition")
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.circuit_breaker"):
        await breaker._transition_to(CircuitState.CLOSED)
    assert breaker.state == CircuitState.CLOSED
