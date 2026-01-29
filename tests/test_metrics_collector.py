from __future__ import annotations

import asyncio

import pytest

from pyoutlineapi import common_types as common_types_module
from pyoutlineapi import metrics_collector as metrics_collector_module
from pyoutlineapi.metrics_collector import (
    MetricsCollector,
    MetricsSnapshot,
    PrometheusExporter,
    UsageStats,
)


class DummyClient:
    async def get_server_info(self, *, as_json: bool = False):
        return {"name": "srv"}

    async def get_transfer_metrics(self, *, as_json: bool = False):
        return {"bytesTransferredByUserId": {"u1": 100, "u2": 50}}

    async def get_access_keys(self, *, as_json: bool = False):
        return {"accessKeys": [{"id": "key"}]}

    async def get_experimental_metrics(self, since: str, *, as_json: bool = False):
        return {
            "server": {
                "tunnelTime": {"seconds": 1},
                "dataTransferred": {"bytes": 1},
                "bandwidth": {
                    "current": {"data": {"bytes": 1}, "timestamp": 1},
                    "peak": {"data": {"bytes": 1}, "timestamp": 1},
                },
                "locations": [],
            },
            "accessKeys": [],
        }


class FailingClient(DummyClient):
    async def get_server_info(self, *, as_json: bool = False):
        raise RuntimeError("fail")


class WeirdTransferClient(DummyClient):
    async def get_transfer_metrics(self, *, as_json: bool = False):
        return {"bytesTransferredByUserId": ["bad"]}


@pytest.mark.asyncio
async def test_collect_single_snapshot():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    snapshot = await collector._collect_single_snapshot()
    assert snapshot is not None
    assert snapshot.key_count == 1
    assert snapshot.total_bytes_transferred == 150


@pytest.mark.asyncio
async def test_collect_single_snapshot_non_dict_transfer():
    collector = MetricsCollector(WeirdTransferClient(), interval=1.0, max_history=5)
    snapshot = await collector._collect_single_snapshot()
    assert snapshot is not None
    assert snapshot.total_bytes_transferred == 0


@pytest.mark.asyncio
async def test_collect_single_snapshot_error(monkeypatch):
    collector = MetricsCollector(FailingClient(), interval=1.0, max_history=5)

    def fake_getsizeof(_):  # type: ignore[no-untyped-def]
        return 10 * 1024 * 1024 + 1

    monkeypatch.setattr("sys.getsizeof", fake_getsizeof)
    snapshot = await collector._collect_single_snapshot()
    assert snapshot is None


def test_metrics_snapshot_size_limit(monkeypatch):
    monkeypatch.setattr(common_types_module.Constants, "MAX_SNAPSHOT_SIZE_MB", 0)
    with pytest.raises(ValueError):
        MetricsSnapshot(
            timestamp=0.0,
            server_info={"a": {"b": {"c": "d"}}},
            transfer_metrics={},
            experimental_metrics={},
            key_count=0,
            total_bytes_transferred=0,
        )


def test_estimate_size_early_exit():
    size = metrics_collector_module._estimate_size({"a": [1, 2, 3]}, max_bytes=1)
    assert size > 1


@pytest.mark.asyncio
async def test_collector_start_stop():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    await collector.start()
    await asyncio.sleep(0)
    await collector.stop()
    assert collector.is_running is False


def test_collector_stats_and_prometheus():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    snapshot = MetricsSnapshot(
        timestamp=1.0,
        server_info={"metricsEnabled": True, "portForNewAccessKeys": 1234},
        transfer_metrics={"bytesTransferredByUserId": {"u1": 10}},
        experimental_metrics={
            "server": {
                "tunnelTime": {"seconds": 1},
                "dataTransferred": {"bytes": 5},
                "bandwidth": {
                    "current": {"data": {"bytes": 1}, "timestamp": 1},
                    "peak": {"data": {"bytes": 2}, "timestamp": 2},
                },
                "locations": [
                    {
                        "location": "US",
                        "tunnelTime": {"seconds": 1},
                        "dataTransferred": {"bytes": 1},
                    }
                ],
            },
            "accessKeys": [
                {
                    "accessKeyId": "u1",
                    "tunnelTime": {"seconds": 1},
                    "dataTransferred": {"bytes": 1},
                    "connection": {
                        "lastTrafficSeen": 1,
                        "peakDeviceCount": {"data": 1, "timestamp": 1},
                    },
                }
            ],
        },
        key_count=1,
        total_bytes_transferred=10,
    )
    collector._history.append(snapshot)
    collector._history.append(
        MetricsSnapshot(
            timestamp=2.0,
            server_info={},
            transfer_metrics={"bytesTransferredByUserId": {}},
            experimental_metrics={},
            key_count=0,
            total_bytes_transferred=0,
        )
    )

    latest = collector.get_latest_snapshot()
    assert latest is not None

    stats = collector.get_usage_stats()
    assert stats.snapshots_count == 2

    filtered = collector.get_snapshots(start_time=1.5)
    assert len(filtered) == 1

    prom = collector.export_prometheus(include_per_key=True)
    assert "outline_keys_total" in prom

    summary = collector.export_prometheus_summary()
    assert "outline_bytes_transferred_total" in summary


def test_metrics_snapshot_and_usage_stats_dict():
    snapshot = MetricsSnapshot(
        timestamp=1.0,
        server_info={"a": 1},
        transfer_metrics={"bytesTransferredByUserId": {"k": 1}},
        experimental_metrics={},
        key_count=1,
        total_bytes_transferred=1,
    )
    assert snapshot.to_dict()["keys_count"] == 1

    stats = UsageStats(
        period_start=1.0,
        period_end=3.0,
        snapshots_count=2,
        total_bytes_transferred=2048,
        avg_bytes_per_snapshot=1024.0,
        peak_bytes=2048,
        active_keys=frozenset({"a"}),
    )
    data = stats.to_dict()
    assert data["active_keys_count"] == 1
    assert stats.megabytes_transferred > 0
    assert stats.gigabytes_transferred > 0


def test_prometheus_exporter_cache():
    exporter = PrometheusExporter()
    metrics = [
        ("metric_name", 1, "gauge", "desc", {"key": "value"}),
    ]
    out1 = exporter.format_metrics_batch(metrics, cache_key="a")
    out2 = exporter.format_metrics_batch(metrics, cache_key="a")
    assert out1 == out2
    exporter.clear_cache()
    out3 = exporter.format_metrics_batch(metrics, cache_key="a")
    assert out3 == out1


def test_collector_empty_history():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    assert collector.get_latest_snapshot() is None
    stats = collector.get_usage_stats()
    assert stats.snapshots_count == 0
    assert collector.export_prometheus() == ""
    assert collector.export_prometheus_summary() == ""


def test_collector_invalid_params():
    with pytest.raises(ValueError):
        MetricsCollector(DummyClient(), interval=0.0)
    with pytest.raises(ValueError):
        MetricsCollector(DummyClient(), interval=1.0, max_history=0)


@pytest.mark.asyncio
async def test_collect_loop_cancel_and_timeout(monkeypatch):
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    collector._interval = 0.01

    async def return_none(self):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.1)
        return None

    monkeypatch.setattr(MetricsCollector, "_collect_single_snapshot", return_none)
    collector._running = True
    task = asyncio.create_task(collector._collect_loop())
    await asyncio.sleep(0.01)
    task.cancel()
    await task
    assert task.done()


@pytest.mark.asyncio
async def test_collect_loop_unexpected_error(monkeypatch):
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    collector._interval = 0.01

    async def boom(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(MetricsCollector, "_collect_single_snapshot", boom)
    collector._running = True
    task = asyncio.create_task(collector._collect_loop())
    await asyncio.sleep(0.005)
    collector._shutdown_event.set()
    await task


@pytest.mark.asyncio
async def test_collector_start_twice_and_stop_not_running(monkeypatch):
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    await collector.start()
    with pytest.raises(RuntimeError):
        await collector.start()
    await collector.stop()
    await collector.stop()


@pytest.mark.asyncio
async def test_collector_stop_timeout(monkeypatch):
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)

    async def fake_loop():  # type: ignore[no-untyped-def]
        await asyncio.sleep(1)

    collector._task = asyncio.create_task(fake_loop())
    collector._running = True

    async def raise_timeout(_task, timeout):  # type: ignore[no-untyped-def]
        raise TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", raise_timeout)
    await collector.stop()


def test_collector_clear_history():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    collector._history.append(
        MetricsSnapshot(
            timestamp=1.0,
            server_info={},
            transfer_metrics={},
            experimental_metrics={},
            key_count=0,
            total_bytes_transferred=0,
        )
    )
    collector.clear_history()
    assert collector.snapshots_count == 0


def test_get_snapshots_end_time_and_limit():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    collector._history.extend(
        [
            MetricsSnapshot(
                timestamp=1.0,
                server_info={},
                transfer_metrics={},
                experimental_metrics={},
                key_count=0,
                total_bytes_transferred=0,
            ),
            MetricsSnapshot(
                timestamp=2.0,
                server_info={},
                transfer_metrics={},
                experimental_metrics={},
                key_count=0,
                total_bytes_transferred=0,
            ),
            MetricsSnapshot(
                timestamp=3.0,
                server_info={},
                transfer_metrics={},
                experimental_metrics={},
                key_count=0,
                total_bytes_transferred=0,
            ),
        ]
    )
    assert len(collector.get_snapshots(end_time=2.0)) == 2
    assert len(collector.get_snapshots(limit=1)) == 1


def test_export_prometheus_with_locations_and_keys():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    snapshot = MetricsSnapshot(
        timestamp=1.0,
        server_info={"metricsEnabled": True, "portForNewAccessKeys": 1234},
        transfer_metrics={"bytesTransferredByUserId": {"u1": 10}},
        experimental_metrics={
            "server": {
                "tunnelTime": {"seconds": 3600},
                "bandwidth": {
                    "current": {"data": {"bytes": 1}},
                    "peak": {"data": {"bytes": 2}},
                },
                "locations": [
                    {
                        "location": "US",
                        "tunnelTime": {"seconds": 1},
                        "dataTransferred": {"bytes": 1},
                    },
                    "invalid",
                    {
                        "location": "EU",
                        "tunnelTime": {"seconds": 0},
                        "dataTransferred": {"bytes": 0},
                    },
                ],
            }
        },
        key_count=1,
        total_bytes_transferred=10,
    )
    collector._history.append(snapshot)
    metrics = collector.export_prometheus(include_per_key=True)
    assert "outline_key_bytes_total" in metrics


@pytest.mark.asyncio
async def test_collector_uptime_and_context_manager():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=5)
    assert collector.uptime == 0.0
    async with collector:
        assert collector.is_running is True
    assert collector.is_running is False
