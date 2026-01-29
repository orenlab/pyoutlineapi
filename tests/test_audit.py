from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

import pytest

from pyoutlineapi.audit import (
    AuditContext,
    DefaultAuditLogger,
    NoOpAuditLogger,
    _sanitize_details,
    audited,
    get_audit_logger,
    get_or_create_audit_logger,
    set_audit_logger,
)


class DummyLogger:
    def __init__(self) -> None:
        self.logged: list[tuple[str, str]] = []
        self.alogged: list[tuple[str, str]] = []

    def log_action(self, action: str, resource: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.logged.append((action, resource))

    async def alog_action(self, action: str, resource: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.alogged.append((action, resource))


class DummyResult:
    def __init__(self, value: str) -> None:
        self.id = value


class SyncExample:
    def __init__(self, logger: DummyLogger) -> None:
        self._audit_logger_instance = logger

    @property
    def _audit_logger(self) -> DummyLogger:
        return self._audit_logger_instance

    @audited()
    def do(self, name: str) -> DummyResult:
        return DummyResult(name)

    @audited(log_success=False, log_failure=True)
    def fail(self, name: str) -> DummyResult:
        raise RuntimeError(f"bad {name}")


class AsyncExample:
    def __init__(self, logger: DummyLogger) -> None:
        self._audit_logger_instance = logger

    @property
    def _audit_logger(self) -> DummyLogger:
        return self._audit_logger_instance

    @audited()
    async def do(self, name: str) -> DummyResult:
        return DummyResult(name)

    @audited(log_success=False, log_failure=True)
    async def fail(self, name: str) -> DummyResult:
        raise RuntimeError(f"bad {name}")


@pytest.mark.asyncio
async def test_audited_async_logs_success():
    logger = DummyLogger()
    obj = AsyncExample(logger)
    result = await obj.do("res")
    assert result.id == "res"
    await asyncio.sleep(0)
    assert ("do", "res") in logger.alogged


def test_audited_sync_logs_success():
    logger = DummyLogger()
    obj = SyncExample(logger)
    result = obj.do("res")
    assert result.id == "res"
    assert ("do", "res") in logger.logged


def test_audit_logger_context():
    logger = DummyLogger()
    set_audit_logger(logger)
    assert get_audit_logger() is logger


def test_sanitize_details_masks():
    details = {"password": "x", "nested": {"token": "y"}}
    sanitized = _sanitize_details(details)
    assert sanitized["password"] == "***REDACTED***"
    assert sanitized["nested"]["token"] == "***REDACTED***"


def test_sanitize_details_no_change_returns_same():
    details = {"count": 1, "nested": {"ok": "x"}}
    sanitized = _sanitize_details(details)
    assert sanitized is details


def test_sanitize_details_empty():
    assert _sanitize_details({}) == {}


def test_audit_context_resource_extraction():
    def sample(key_id: str):  # type: ignore[no-untyped-def]
        return key_id

    ctx = AuditContext.from_call(
        sample, None, args=("id-1",), kwargs={}, result=None, exception=None
    )
    assert ctx.resource == "id-1"


def test_audit_context_resource_patterns():
    def func(key_id: str):  # type: ignore[no-untyped-def]
        return None

    class Obj:
        id = "obj-1"

    ctx = AuditContext.from_call(func, None, (), {"key_id": "k1"}, result=None)
    assert ctx.resource == "k1"

    ctx = AuditContext.from_call(func, None, (), {}, result={"id": "k2"})
    assert ctx.resource == "k2"

    ctx = AuditContext.from_call(func, None, (Obj(),), {}, result=Obj())
    assert ctx.resource == "obj-1"

    def server_action():  # type: ignore[no-untyped-def]
        return None

    ctx = AuditContext.from_call(server_action, None, (), {}, result=None)
    assert ctx.resource == "server"


@pytest.mark.asyncio
async def test_audit_logger_queue_full_fallback(monkeypatch):
    logger_instance = DefaultAuditLogger(queue_size=1)
    entries: list[dict[str, object]] = []

    def fake_write_log(self, entry):  # type: ignore[no-untyped-def]
        entries.append(entry)

    monkeypatch.setattr(DefaultAuditLogger, "_write_log", fake_write_log)

    def fake_put_nowait(_entry):  # type: ignore[no-untyped-def]
        raise asyncio.QueueFull

    monkeypatch.setattr(logger_instance._queue, "put_nowait", fake_put_nowait)

    await logger_instance.alog_action("act", "res")
    assert entries


@pytest.mark.asyncio
async def test_audit_logger_process_queue_timeout_flush(monkeypatch):
    logger_instance = DefaultAuditLogger(batch_size=10, batch_timeout=0.001)
    flushed: list[int] = []

    def fake_write_batch(self, batch):  # type: ignore[no-untyped-def]
        flushed.append(len(batch))

    monkeypatch.setattr(DefaultAuditLogger, "_write_batch", fake_write_batch)
    await logger_instance._queue.put({"action": "a", "resource": "r"})

    task = asyncio.create_task(logger_instance._process_queue())
    await asyncio.sleep(0.01)
    logger_instance._shutdown_event.set()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert flushed


@pytest.mark.asyncio
async def test_audit_logger_process_queue_cancel_flush(monkeypatch):
    logger_instance = DefaultAuditLogger(batch_size=10, batch_timeout=1.0)
    flushed: list[int] = []

    def fake_write_batch(self, batch):  # type: ignore[no-untyped-def]
        flushed.append(len(batch))

    monkeypatch.setattr(DefaultAuditLogger, "_write_batch", fake_write_batch)
    await logger_instance._queue.put({"action": "a", "resource": "r"})

    task = asyncio.create_task(logger_instance._process_queue())
    await asyncio.sleep(0.01)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert flushed


@pytest.mark.asyncio
async def test_audit_logger_shutdown_timeout_logs_warning(caplog):
    logger_instance = DefaultAuditLogger()

    async def slow_join():  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.01)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(logger_instance._queue, "join", slow_join)
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.audit"):
        await logger_instance.shutdown(timeout=0.0001)
    monkeypatch.undo()
    assert any("Queue did not drain" in r.message for r in caplog.records)

def test_audit_context_resource_unknown():
    def op():  # type: ignore[no-untyped-def]
        return None

    ctx = AuditContext.from_call(
        op, None, args=(), kwargs={}, result=None, exception=None
    )
    assert ctx.resource == "unknown"


def test_audit_context_details_extraction():
    def op(name: str, limit: int = 10):  # type: ignore[no-untyped-def]
        return name

    ctx = AuditContext.from_call(
        op, None, args=(), kwargs={"name": "x"}, result=None, exception=None
    )
    assert ctx.details.get("name") == "x"


def test_audit_context_details_for_list():
    def op(items: list[int]):  # type: ignore[no-untyped-def]
        return items

    ctx = AuditContext.from_call(
        op, None, args=(), kwargs={"items": [1, 2, 3]}, result=None, exception=None
    )
    assert ctx.details.get("items") == 3


def test_audit_context_details_for_dict():
    def op(payload: dict[str, object]):  # type: ignore[no-untyped-def]
        return payload

    ctx = AuditContext.from_call(
        op, None, args=(), kwargs={"payload": {"x": 1}}, result=None, exception=None
    )
    assert ctx.details["payload"]["x"] == 1


def test_audit_context_details_model_dump():
    class DummyModel:
        def model_dump(self, **kwargs):  # type: ignore[no-untyped-def]
            return {"x": 1}

    def op(model: DummyModel):  # type: ignore[no-untyped-def]
        return model

    ctx = AuditContext.from_call(
        op, None, args=(), kwargs={"model": DummyModel()}, result=None, exception=None
    )
    assert ctx.details["model"]["x"] == 1


def test_default_audit_logger_is_singleton():
    logger1 = get_or_create_audit_logger()
    logger2 = get_or_create_audit_logger()
    assert logger1 is logger2

    default_logger = DefaultAuditLogger()
    default_logger.log_action("act", "res")


def test_get_or_create_audit_logger_cache():
    logger1 = get_or_create_audit_logger(instance_id=1)
    logger2 = get_or_create_audit_logger(instance_id=1)
    assert logger1 is logger2


def test_get_or_create_audit_logger_context_override():
    logger = DummyLogger()
    set_audit_logger(logger)
    assert get_or_create_audit_logger(instance_id=2) is logger


@pytest.mark.asyncio
async def test_noop_audit_logger():
    logger = NoOpAuditLogger()
    logger.log_action("a", "r")
    await logger.alog_action("a", "r")


@pytest.mark.asyncio
async def test_default_audit_logger_async_queue(monkeypatch):
    logger = DefaultAuditLogger(queue_size=10, batch_size=1, batch_timeout=0.01)

    # Ensure background task runs and processes the item
    await logger.alog_action("act", "res", details={"password": "x"})
    await asyncio.sleep(0.02)
    await logger.shutdown()


@pytest.mark.asyncio
async def test_audited_failure_paths():
    logger = DummyLogger()
    obj = AsyncExample(logger)
    with pytest.raises(RuntimeError):
        await obj.fail(name="res")
    await asyncio.sleep(0)
    assert ("fail", "res") in logger.alogged

    sync_obj = SyncExample(logger)
    with pytest.raises(RuntimeError):
        sync_obj.fail(name="res")
    assert ("fail", "res") in logger.logged


@pytest.mark.asyncio
async def test_default_audit_logger_queue_full(monkeypatch):
    logger = DefaultAuditLogger(queue_size=1, batch_size=10, batch_timeout=1.0)
    entries: list[dict[str, object]] = []

    def capture(self, entry):  # type: ignore[no-untyped-def]
        entries.append(entry)

    monkeypatch.setattr(DefaultAuditLogger, "_write_log", capture)
    logger._queue.put_nowait({"action": "a", "resource": "r"})
    await logger.alog_action("act", "res")
    assert any(e.get("action") == "act" for e in entries)


@pytest.mark.asyncio
async def test_default_audit_logger_fallback_on_shutdown(monkeypatch):
    logger = DefaultAuditLogger(queue_size=1, batch_size=1, batch_timeout=0.01)
    entries: list[dict[str, object]] = []

    def capture(self, entry):  # type: ignore[no-untyped-def]
        entries.append(entry)

    monkeypatch.setattr(DefaultAuditLogger, "_write_log", capture)
    logger._shutdown_event.set()
    await logger.alog_action("act", "res", user="u", correlation_id="cid")
    assert any(e.get("user") == "u" for e in entries)


def test_format_message_with_user_and_correlation():
    entry = {
        "action": "act",
        "resource": "res",
        "user": "u",
        "correlation_id": "cid",
    }
    msg = DefaultAuditLogger._format_message(entry)
    assert "[AUDIT]" in msg
    assert "u" in msg
    assert "cid" in msg


@pytest.mark.asyncio
async def test_default_audit_logger_ensure_task_running_fast_path():
    logger = DefaultAuditLogger(queue_size=10, batch_size=10, batch_timeout=0.01)
    await logger._ensure_task_running()
    task = logger._task
    assert task is not None
    await logger._ensure_task_running()
    await logger.shutdown()


def test_audited_sync_without_logger():
    class NoLogger:
        @audited()
        def do(self):  # type: ignore[no-untyped-def]
            return "ok"

    obj = NoLogger()
    assert obj.do() == "ok"


@pytest.mark.asyncio
async def test_default_audit_logger_shutdown_debug(caplog):
    logger = DefaultAuditLogger(queue_size=10, batch_size=1, batch_timeout=0.01)
    await logger.alog_action("act", "res")
    await asyncio.sleep(0.02)
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.audit"):
        await logger.shutdown()


@pytest.mark.asyncio
async def test_default_audit_logger_cancel_flush(monkeypatch):
    logger = DefaultAuditLogger(queue_size=10, batch_size=10, batch_timeout=0.1)
    entries: list[dict[str, object]] = []

    def capture(self, entry):  # type: ignore[no-untyped-def]
        entries.append(entry)

    monkeypatch.setattr(DefaultAuditLogger, "_write_log", capture)
    await logger._ensure_task_running()
    logger._queue.put_nowait(logger._build_entry("act", "res", None, None, None))
    await asyncio.sleep(0.02)
    task = logger._task
    assert task is not None
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    assert entries


@pytest.mark.asyncio
async def test_default_audit_logger_shutdown_timeout(monkeypatch):
    logger = DefaultAuditLogger(queue_size=10, batch_size=100, batch_timeout=1.0)
    logger._queue.put_nowait({"action": "a", "resource": "r"})

    async def fake_join():  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)
        raise asyncio.TimeoutError()

    monkeypatch.setattr(logger._queue, "join", fake_join)
    await logger.shutdown(timeout=0.01)
