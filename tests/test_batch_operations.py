from __future__ import annotations

import asyncio
import logging

import pytest

from pyoutlineapi.batch_operations import (
    BatchOperations,
    BatchProcessor,
    BatchResult,
    ValidationHelper,
)
from pyoutlineapi.models import AccessKey, DataLimit


class DummyClient:
    async def create_access_key(self, **kwargs):  # type: ignore[no-untyped-def]
        return AccessKey(
            id="key-1",
            name=kwargs.get("name"),
            password="pwd",
            port=12345,
            method="aes-256-gcm",
            accessUrl="ss://example",
            dataLimit=None,
        )

    async def delete_access_key(self, key_id: str) -> bool:
        return True

    async def rename_access_key(self, key_id: str, name: str) -> bool:
        return True

    async def set_access_key_data_limit(self, key_id: str, limit: DataLimit) -> bool:
        return True

    async def get_access_key(self, key_id: str):
        return AccessKey(
            id=key_id,
            name="Name",
            password="pwd",
            port=12345,
            method="aes-256-gcm",
            accessUrl="ss://example",
            dataLimit=None,
        )


@pytest.mark.asyncio
async def test_batch_processor_success_and_fail():
    processor: BatchProcessor[int, int] = BatchProcessor(max_concurrent=2)

    async def double(x: int) -> int:
        return x * 2

    results = await processor.process([1, 2, 3], double)
    assert results == [2, 4, 6]

    async def fail(x: int):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"bad {x}")

    results = await processor.process([1], fail, fail_fast=False)
    assert isinstance(results[0], Exception)

    assert await processor.process([], double) == []


@pytest.mark.asyncio
async def test_batch_processor_cancels_pending_tasks():
    processor: BatchProcessor[int, int] = BatchProcessor(max_concurrent=2)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def worker(value: int) -> int:
        if value == 1:
            started.set()
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return value
        await started.wait()
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await processor.process([1, 2], worker, fail_fast=True)

    await asyncio.wait_for(cancelled.wait(), timeout=0.2)


def test_validation_helper_config():
    helper = ValidationHelper()
    config = {"name": " test ", "port": 12345}
    validated = helper.validate_config_dict(config, 0, fail_fast=True)
    assert validated is not None
    assert validated["name"] == "test"
    assert helper.validate_config_dict("bad", 0, fail_fast=False) is None  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        helper.validate_config_dict("bad", 0, fail_fast=True)  # type: ignore[arg-type]
    assert helper.validate_config_dict({"name": " "}, 0, fail_fast=False) is None
    with pytest.raises(ValueError):
        helper.validate_config_dict({"name": " "}, 0, fail_fast=True)
    validated = helper.validate_config_dict({"port": 12345}, 0, fail_fast=True)
    assert validated is not None


def test_validation_helper_tuple_pair():
    helper = ValidationHelper()
    assert helper.validate_tuple_pair(("a", "b"), 0, (str, str), False) == ("a", "b")
    assert helper.validate_tuple_pair(("a", 1), 0, (str, str), False) is None
    with pytest.raises(ValueError):
        helper.validate_tuple_pair(("a",), 0, (str, str), True)
    with pytest.raises(ValueError):
        helper.validate_tuple_pair(("a", 1), 0, (str, str), True)


def test_validation_helper_key_id():
    helper = ValidationHelper()
    assert helper.validate_key_id("key-1", 0, False) == "key-1"
    assert helper.validate_key_id(123, 0, False) is None  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        helper.validate_key_id(123, 0, True)  # type: ignore[arg-type]
    assert helper.validate_key_id("bad id", 0, False) is None
    with pytest.raises(ValueError):
        helper.validate_key_id("bad id", 0, True)


def test_batch_result_properties():
    result = BatchResult(
        total=2,
        successful=1,
        failed=1,
        results=(1, Exception("x")),
        errors=("x",),
        validation_errors=(),
    )
    assert result.success_rate == 0.5
    assert result.has_errors is True
    assert result.has_validation_errors is False
    assert result.get_successful_results() == [1]
    assert len(result.get_failures()) == 1
    data = result.to_dict()
    assert data["total"] == 2
    empty = BatchResult[int](
        total=0,
        successful=0,
        failed=0,
        results=(),
        errors=(),
        validation_errors=(),
    )
    assert empty.success_rate == 1.0


@pytest.mark.asyncio
async def test_batch_operations_create_and_fetch():
    ops = BatchOperations(DummyClient())
    result = await ops.create_multiple_keys([{"name": "Alice"}], fail_fast=False)
    assert result.total == 1
    assert result.successful == 1

    fetched = await ops.fetch_multiple_keys(["key-1"], fail_fast=False)
    assert fetched.total == 1
    assert fetched.successful == 1

    empty = await ops.fetch_multiple_keys([])
    assert empty.total == 0
    empty_create = await ops.create_multiple_keys([])
    assert empty_create.total == 0


@pytest.mark.asyncio
async def test_batch_operations_other_actions():
    ops = BatchOperations(DummyClient())

    delete_result = await ops.delete_multiple_keys(["key-1"], fail_fast=False)
    assert delete_result.successful == 1

    rename_result = await ops.rename_multiple_keys([("key-1", "New")])
    assert rename_result.successful == 1

    limit_result = await ops.set_multiple_data_limits([("key-1", 100)])
    assert limit_result.successful == 1

    empty = await ops.delete_multiple_keys([])
    assert empty.total == 0
    empty_rename = await ops.rename_multiple_keys([])
    assert empty_rename.total == 0
    empty_limits = await ops.set_multiple_data_limits([])
    assert empty_limits.total == 0


@pytest.mark.asyncio
async def test_batch_fail_fast_and_custom_ops():
    ops = BatchOperations(DummyClient(), max_concurrent=1)

    async def bad(_):  # type: ignore[no-untyped-def]
        raise RuntimeError("fail")

    processor: BatchProcessor[int, int] = BatchProcessor(max_concurrent=1)
    with pytest.raises(RuntimeError):
        await processor.process([1], bad, fail_fast=True)

    async def ok():
        return 1

    custom = await ops.execute_custom_operations([ok])
    assert custom.successful == 1

    async def fail_op():
        raise RuntimeError("boom")

    result = await ops.execute_custom_operations([fail_op], fail_fast=False)
    assert result.failed == 1


@pytest.mark.asyncio
async def test_batch_operations_validation_errors():
    ops = BatchOperations(DummyClient())
    result = await ops.create_multiple_keys([{"name": " "}], fail_fast=False)
    assert result.failed == 1
    assert result.has_validation_errors is True

    result = await ops.rename_multiple_keys([("bad id", "")], fail_fast=False)
    assert result.has_errors is True

    result = await ops.set_multiple_data_limits([("bad", -1)], fail_fast=False)
    assert result.failed >= 1

    result = await ops.rename_multiple_keys([("bad",)], fail_fast=False)  # type: ignore[list-item]
    assert result.failed >= 1

    result = await ops.set_multiple_data_limits([("key-1", "bad")], fail_fast=False)  # type: ignore[list-item]
    assert result.failed >= 1
    with pytest.raises(ValueError):
        await ops.rename_multiple_keys([("bad id", "")], fail_fast=True)
    with pytest.raises(ValueError):
        await ops.set_multiple_data_limits([("bad", -1)], fail_fast=True)


@pytest.mark.asyncio
async def test_batch_operations_invalid_tuple_types(monkeypatch):
    ops = BatchOperations(DummyClient())

    def bad_validate(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return (123, "name")

    monkeypatch.setattr(
        ValidationHelper, "validate_tuple_pair", staticmethod(bad_validate)
    )
    result = await ops.rename_multiple_keys([("key-1", "new")], fail_fast=False)
    assert result.validation_errors

    def bad_validate_limits(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return ("key-1", "bad")

    monkeypatch.setattr(
        ValidationHelper, "validate_tuple_pair", staticmethod(bad_validate_limits)
    )
    result = await ops.set_multiple_data_limits([("key-1", 1)], fail_fast=False)
    assert result.validation_errors


@pytest.mark.asyncio
async def test_batch_concurrency_and_custom_ops_empty():
    ops = BatchOperations(DummyClient())
    await ops.set_concurrency(2)
    empty = await ops.execute_custom_operations([])
    assert empty.total == 0


@pytest.mark.asyncio
async def test_batch_operations_invalid_concurrency():
    with pytest.raises(ValueError):
        BatchOperations(DummyClient(), max_concurrent=0)


def test_batch_processor_invalid_concurrency():
    with pytest.raises(ValueError):
        BatchProcessor(max_concurrent=0)


@pytest.mark.asyncio
async def test_batch_processor_set_concurrency_logs(caplog):
    processor = BatchProcessor(max_concurrent=1)
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.batch_operations"):
        await processor.set_concurrency(2)
    assert any("concurrency changed" in r.message for r in caplog.records)
    await processor.set_concurrency(2)
    with pytest.raises(ValueError):
        await processor.set_concurrency(0)


@pytest.mark.asyncio
async def test_batch_operations_invalid_ids():
    ops = BatchOperations(DummyClient())
    result = await ops.delete_multiple_keys(["bad id"], fail_fast=False)
    assert result.failed >= 1
    result = await ops.fetch_multiple_keys(["bad id"], fail_fast=False)
    assert result.failed >= 1
