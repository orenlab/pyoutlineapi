from __future__ import annotations

import asyncio
import logging
from collections import deque

import pytest

from pyoutlineapi.metrics_collector import (
    MetricsCollector,
    MetricsSnapshot,
    PrometheusExporter,
)


class DummyClient:
    async def get_server_info(self, *, as_json: bool = False):  # type: ignore[no-untyped-def]
        return {"metricsEnabled": True, "portForNewAccessKeys": 8080}

    async def get_transfer_metrics(self, *, as_json: bool = False):  # type: ignore[no-untyped-def]
        return {"bytesTransferredByUserId": {"a": 1, "b": 0}}

    async def get_access_keys(self, *, as_json: bool = False):  # type: ignore[no-untyped-def]
        return {"accessKeys": [{"id": "a"}]}

    async def get_experimental_metrics(self, since, *, as_json: bool = False):  # type: ignore[no-untyped-def]
        return {
            "server": {
                "tunnelTime": {"seconds": 3600},
                "bandwidth": {
                    "current": {"data": {"bytes": 10}},
                    "peak": {"data": {"bytes": 20}},
                },
                "locations": [
                    {
                        "location": "us",
                        "dataTransferred": {"bytes": 5},
                        "tunnelTime": {"seconds": 7},
                    }
                ],
            }
        }


class FailingClient(DummyClient):
    async def get_server_info(self, *, as_json: bool = False):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


class FailingKeysClient(DummyClient):
    async def get_access_keys(self, *, as_json: bool = False):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


def _make_snapshot(timestamp: float, total_bytes: int) -> MetricsSnapshot:
    return MetricsSnapshot(
        timestamp=timestamp,
        server_info={"metricsEnabled": True, "portForNewAccessKeys": 1234},
        transfer_metrics={"bytesTransferredByUserId": {"a": total_bytes}},
        experimental_metrics={},
        key_count=1,
        total_bytes_transferred=total_bytes,
    )


def _make_snapshot_with_experimental(timestamp: float) -> MetricsSnapshot:
    return MetricsSnapshot(
        timestamp=timestamp,
        server_info={"metricsEnabled": True, "portForNewAccessKeys": 1234},
        transfer_metrics={"bytesTransferredByUserId": {"a": 1024}},
        experimental_metrics={
            "server": {
                "tunnelTime": {"seconds": 3600},
                "bandwidth": {
                    "current": {"data": {"bytes": 10}},
                    "peak": {"data": {"bytes": 20}},
                },
                "locations": [
                    {
                        "location": "us",
                        "dataTransferred": {"bytes": 5},
                        "tunnelTime": {"seconds": 7},
                    }
                ],
            }
        },
        key_count=2,
        total_bytes_transferred=1024,
    )


def test_prometheus_exporter_cache_and_clear():
    exporter = PrometheusExporter(cache_ttl=60)
    metrics = [("test_metric", 1, "gauge", "help", None)]
    out1 = exporter.format_metrics_batch(metrics, cache_key="k1")
    out2 = exporter.format_metrics_batch(metrics, cache_key="k1")
    assert out1 == out2
    exporter.clear_cache()
    out3 = exporter.format_metrics_batch(metrics, cache_key="k1")
    assert out3 == out1


def test_prometheus_exporter_no_cache_key():
    exporter = PrometheusExporter(cache_ttl=60)
    metrics = [("test_metric", 1, "gauge", "", None)]
    out = exporter.format_metrics_batch(metrics, cache_key=None)
    assert "test_metric" in out


def test_prometheus_format_metric_with_labels():
    exporter = PrometheusExporter(cache_ttl=60)
    lines = exporter.format_metric(
        "metric",
        1,
        metric_type="gauge",
        help_text="help",
        labels={"key": "value"},
    )
    assert any("HELP metric help" in line for line in lines)
    assert any('metric{key="value"} 1' in line for line in lines)


@pytest.mark.asyncio
async def test_collect_single_snapshot_with_fallbacks():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    snapshot = await collector._collect_single_snapshot()
    assert snapshot is not None
    assert snapshot.key_count == 1

    collector_fail = MetricsCollector(FailingClient(), interval=1.0, max_history=10)
    snapshot2 = await collector_fail._collect_single_snapshot()
    assert snapshot2 is not None
    assert snapshot2.key_count == 1

    collector_fail_keys = MetricsCollector(
        FailingKeysClient(), interval=1.0, max_history=10
    )
    snapshot3 = await collector_fail_keys._collect_single_snapshot()
    assert snapshot3 is not None
    assert snapshot3.key_count == 0


@pytest.mark.asyncio
async def test_collect_single_snapshot_exception_returns_none(monkeypatch):
    class BadDict(dict):
        def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise ValueError("bad")

    class BadKeysClient(DummyClient):
        async def get_access_keys(self, *, as_json: bool = False):  # type: ignore[no-untyped-def]
            return BadDict()

    collector = MetricsCollector(BadKeysClient(), interval=1.0, max_history=10)
    assert await collector._collect_single_snapshot() is None


def test_get_snapshots_filters_and_latest():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque(
        [
            _make_snapshot(1.0, 10),
            _make_snapshot(2.0, 20),
            _make_snapshot(3.0, 30),
        ],
        maxlen=10,
    )

    assert collector.get_latest_snapshot().total_bytes_transferred == 30
    assert len(collector.get_snapshots(start_time=2.0)) == 2
    assert len(collector.get_snapshots(end_time=2.0)) == 2
    assert len(collector.get_snapshots(limit=1)) == 1


def test_usage_stats_caching():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque([_make_snapshot(1.0, 10)], maxlen=10)
    stats1 = collector.get_usage_stats()
    stats2 = collector.get_usage_stats()
    assert stats1 is stats2


def test_usage_stats_empty_history():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    stats = collector.get_usage_stats()
    assert stats.total_bytes_transferred == 0


def test_export_prometheus_and_summary():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque([_make_snapshot_with_experimental(1.0)], maxlen=10)
    output = collector.export_prometheus(include_per_key=True)
    assert "outline_keys_total" in output
    assert "outline_key_bytes_total" in output
    assert "outline_tunnel_time_seconds_total" in output
    assert "outline_bandwidth_peak_bytes" in output

    summary = collector.export_prometheus_summary()
    assert "outline_bytes_per_second" in summary


def test_clear_history_resets_state(caplog):
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque([_make_snapshot(1.0, 10)], maxlen=10)
    collector._stats_cache = collector.get_usage_stats()
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.metrics_collector"):
        collector.clear_history()
    assert collector.snapshots_count == 0
    assert collector.get_latest_snapshot() is None


@pytest.mark.asyncio
async def test_collect_loop_warning_and_stop(caplog):
    class ErrorCollector(MetricsCollector):
        async def _collect_single_snapshot(self):  # type: ignore[no-untyped-def]
            return None

    collector = ErrorCollector(DummyClient(), interval=1.0, max_history=10)
    collector._interval = 0.001
    collector._running = True

    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.metrics_collector"):
        task = asyncio.create_task(collector._collect_loop())
        await asyncio.sleep(0.05)
        collector._shutdown_event.set()
        
        try:
            await asyncio.wait_for(task, timeout=0.1)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    assert any("Failed to collect metrics" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_start_and_stop():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    await collector.start()
    assert collector.is_running is True
    await collector.stop()
    assert collector.is_running is False


def test_uptime_when_running():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._running = True
    collector._start_time = 1.0
    assert collector.uptime >= 0.0


def test_export_prometheus_no_snapshot():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history.clear()
    assert collector.export_prometheus() == ""


def test_export_prometheus_without_per_key_or_experimental():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque(
        [
            MetricsSnapshot(
                timestamp=1.0,
                server_info={},
                transfer_metrics={},
                experimental_metrics={},
                key_count=0,
                total_bytes_transferred=0,
            )
        ],
        maxlen=10,
    )
    output = collector.export_prometheus(include_per_key=False)
    assert "outline_keys_total" in output


def test_export_prometheus_per_key_non_dict():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque(
        [
            MetricsSnapshot(
                timestamp=1.0,
                server_info={"metricsEnabled": False},
                transfer_metrics={"bytesTransferredByUserId": []},
                experimental_metrics={},
                key_count=0,
                total_bytes_transferred=0,
            )
        ],
        maxlen=10,
    )
    output = collector.export_prometheus(include_per_key=True)
    assert "outline_metrics_enabled" in output


def test_export_prometheus_experimental_zero_location():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque(
        [
            MetricsSnapshot(
                timestamp=1.0,
                server_info={"metricsEnabled": True},
                transfer_metrics={"bytesTransferredByUserId": {"a": 1}},
                experimental_metrics={
                    "server": {
                        "locations": [
                            {"location": "zero", "dataTransferred": {"bytes": 0}}
                        ],
                        "bandwidth": {"current": {"data": {}}},
                    }
                },
                key_count=1,
                total_bytes_transferred=1,
            )
        ],
        maxlen=10,
    )
    output = collector.export_prometheus(include_per_key=True)
    assert "outline_keys_total" in output


@pytest.mark.asyncio
async def test_stop_cancels_task(caplog):
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)

    async def long_task():  # type: ignore[no-untyped-def]
        await asyncio.sleep(1)

    collector._running = True
    collector._task = asyncio.create_task(long_task())
    collector._shutdown_event.clear()

    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.metrics_collector"):
        await collector.stop()
    assert collector._task is None


def test_get_snapshots_limit_zero():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque([_make_snapshot(1.0, 10)], maxlen=10)
    assert len(collector.get_snapshots(limit=0)) == 1


def test_usage_stats_with_non_dict_bytes():
    collector = MetricsCollector(DummyClient(), interval=1.0, max_history=10)
    collector._history = deque(
        [
            MetricsSnapshot(
                timestamp=1.0,
                server_info={},
                transfer_metrics={"bytesTransferredByUserId": []},
                experimental_metrics={},
                key_count=0,
                total_bytes_transferred=0,
            )
        ],
        maxlen=10,
    )
    stats = collector.get_usage_stats()
    assert stats.active_keys == frozenset()
