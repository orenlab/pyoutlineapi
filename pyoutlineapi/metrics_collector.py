"""PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

from __future__ import annotations

import asyncio
import bisect
import logging
import sys
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from typing import TYPE_CHECKING, Any, Final

from .common_types import Constants

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import Self

    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)

# Constants
_MIN_INTERVAL: Final[float] = 1.0
_MAX_INTERVAL: Final[float] = 3600.0
_MAX_HISTORY: Final[int] = 100_000
_PROMETHEUS_CACHE_TTL: Final[int] = 30  # seconds


def _log_if_enabled(level: int, message: str) -> None:
    """Centralized logging with level check.

    :param level: Logging level
    :param message: Log message
    """
    if logger.isEnabledFor(level):
        logger.log(level, message)


@dataclass(slots=True, frozen=True)
class MetricsSnapshot:
    """Immutable metrics snapshot with size validation."""

    timestamp: float
    server_info: dict[str, Any] = field(default_factory=dict)
    transfer_metrics: dict[str, Any] = field(default_factory=dict)
    experimental_metrics: dict[str, Any] = field(default_factory=dict)
    key_count: int = 0
    total_bytes_transferred: int = 0

    def __post_init__(self) -> None:
        """Validate snapshot size.

        :raises ValueError: If snapshot exceeds size limit
        """
        total_size = (
            sys.getsizeof(self.server_info)
            + sys.getsizeof(self.transfer_metrics)
            + sys.getsizeof(self.experimental_metrics)
        )

        max_bytes = Constants.MAX_SNAPSHOT_SIZE_MB * 1024 * 1024

        if total_size > max_bytes:
            msg = (
                f"Snapshot too large: {total_size / 1024 / 1024:.2f} MB "
                f"(max {Constants.MAX_SNAPSHOT_SIZE_MB} MB)"
            )
            raise ValueError(msg)

    @cached_property
    def _dict_cache(self) -> dict[str, Any]:
        """Cached dictionary representation for performance.

        :return: Dictionary representation
        """
        return {
            "timestamp": self.timestamp,
            "server": self.server_info,
            "transfer": self.transfer_metrics,
            "experimental": self.experimental_metrics,
            "keys_count": self.key_count,
            "total_bytes": self.total_bytes_transferred,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary (cached).

        :return: Dictionary representation
        """
        return self._dict_cache


@dataclass(slots=True, frozen=True)
class UsageStats:
    """Immutable usage statistics for a time period.

    Provides comprehensive traffic analysis with optimized calculations.
    """

    period_start: float
    period_end: float
    snapshots_count: int
    total_bytes_transferred: int
    avg_bytes_per_snapshot: float
    peak_bytes: int
    active_keys: frozenset[str] = field(default_factory=frozenset)

    @cached_property
    def duration(self) -> float:
        """Get period duration in seconds (cached).

        :return: Duration in seconds
        """
        return max(0.0, self.period_end - self.period_start)

    @cached_property
    def bytes_per_second(self) -> float:
        """Calculate average bytes per second (cached).

        :return: Bytes per second
        """
        duration = self.duration
        return 0.0 if duration == 0 else self.total_bytes_transferred / duration

    @cached_property
    def megabytes_transferred(self) -> float:
        """Get total in megabytes (cached).

        :return: Total MB transferred
        """
        return self.total_bytes_transferred / (1024**2)

    @cached_property
    def gigabytes_transferred(self) -> float:
        """Get total in gigabytes (cached).

        :return: Total GB transferred
        """
        return self.total_bytes_transferred / (1024**3)

    @cached_property
    def _dict_cache(self) -> dict[str, Any]:
        """Cached dictionary representation.

        :return: Dictionary representation
        """
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "duration": self.duration,
            "snapshots_count": self.snapshots_count,
            "total_bytes_transferred": self.total_bytes_transferred,
            "megabytes_transferred": self.megabytes_transferred,
            "gigabytes_transferred": self.gigabytes_transferred,
            "avg_bytes_per_snapshot": self.avg_bytes_per_snapshot,
            "peak_bytes": self.peak_bytes,
            "bytes_per_second": self.bytes_per_second,
            "active_keys_count": len(self.active_keys),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (cached).

        :return: Dictionary representation
        """
        return self._dict_cache


class PrometheusExporter:
    """Helper class for Prometheus metrics export with caching.

    Optimized for high-frequency exports with minimal overhead.
    """

    __slots__ = ("_cache", "_cache_time", "_cache_ttl")

    def __init__(self, cache_ttl: int = _PROMETHEUS_CACHE_TTL) -> None:
        """Initialize exporter with caching.

        :param cache_ttl: Cache TTL in seconds
        """
        self._cache: dict[str, str] = {}
        self._cache_time: dict[str, float] = {}
        self._cache_ttl = cache_ttl

    @staticmethod
    @lru_cache(maxsize=256)
    def _format_single_metric(
        name: str,
        value: float | int,
        metric_type: str,
        help_text: str,
        labels_tuple: tuple[tuple[str, str], ...] | None,
    ) -> str:
        """Format single Prometheus metric (cached via LRU).

        :param name: Metric name
        :param value: Metric value
        :param metric_type: Metric type
        :param help_text: Help text
        :param labels_tuple: Labels as tuple for hashability
        :return: Formatted metric string
        """
        lines: list[str] = []

        if help_text:
            lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")

        if labels_tuple:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels_tuple)
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")

        return "\n".join(lines)

    def format_metric(
        self,
        name: str,
        value: float | int,
        metric_type: str = "gauge",
        help_text: str = "",
        labels: dict[str, str] | None = None,
    ) -> list[str]:
        """Format single Prometheus metric.

        :param name: Metric name
        :param value: Metric value
        :param metric_type: Metric type
        :param help_text: Help text description
        :param labels: Optional labels dictionary
        :return: List of formatted metric lines
        """
        # Convert labels dict to tuple for caching
        labels_tuple = tuple(sorted(labels.items())) if labels else None
        metric_str = self._format_single_metric(
            name, value, metric_type, help_text, labels_tuple
        )
        return metric_str.split("\n")

    def format_metrics_batch(
        self,
        metrics: Sequence[tuple[str, float | int, str, str, dict[str, str] | None]],
        cache_key: str | None = None,
    ) -> str:
        """Format multiple metrics at once with optional caching.

        :param metrics: Sequence of (name, value, type, help, labels) tuples
        :param cache_key: Optional cache key for result caching
        :return: Formatted Prometheus metrics string
        """
        # Check cache if key provided
        if cache_key:
            current_time = asyncio.get_event_loop().time()
            if cache_key in self._cache:
                cache_age = current_time - self._cache_time.get(cache_key, 0)
                if cache_age < self._cache_ttl:
                    return self._cache[cache_key]

        # Format metrics
        all_lines: list[str] = []
        for name, value, metric_type, help_text, labels in metrics:
            metric_lines = self.format_metric(
                name, value, metric_type, help_text, labels
            )
            all_lines.extend(metric_lines)
            all_lines.append("")  # Empty line between metrics

        result = "\n".join(all_lines)

        # Update cache if key provided
        if cache_key:
            self._cache[cache_key] = result
            self._cache_time[cache_key] = asyncio.get_event_loop().time()

        return result

    def clear_cache(self) -> None:
        """Clear export cache."""
        self._cache.clear()
        self._cache_time.clear()


class MetricsCollector:
    """Metrics collector with optimized performance."""

    __slots__ = (
        "_client",
        "_history",
        "_interval",
        "_max_history",
        "_prometheus_exporter",
        "_running",
        "_shutdown_event",
        "_start_time",
        "_stats_cache",
        "_stats_cache_time",
        "_task",
    )

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        interval: float = 60.0,
        max_history: int = 1440,
    ) -> None:
        """Initialize metrics collector.

        :param client: AsyncOutlineClient instance
        :param interval: Collection interval in seconds
        :param max_history: Maximum snapshots to keep
        :raises ValueError: If parameters invalid
        """
        if not _MIN_INTERVAL <= interval <= _MAX_INTERVAL:
            msg = f"Interval must be between {_MIN_INTERVAL} and {_MAX_INTERVAL}"
            raise ValueError(msg)

        if not 1 <= max_history <= _MAX_HISTORY:
            msg = f"max_history must be between 1 and {_MAX_HISTORY}"
            raise ValueError(msg)

        self._client = client
        self._interval = interval
        self._max_history = max_history

        # Use deque for O(1) append/popleft operations
        self._history: deque[MetricsSnapshot] = deque(maxlen=max_history)

        self._prometheus_exporter = PrometheusExporter()
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._start_time: float = 0.0

        # Stats cache
        self._stats_cache: UsageStats | None = None
        self._stats_cache_time: float = 0.0

    async def _collect_single_snapshot(self) -> MetricsSnapshot | None:
        """Collect a single metrics snapshot.

        :return: MetricsSnapshot or None on error
        """
        try:
            # Gather all metrics concurrently
            server_task = asyncio.create_task(self._client.get_server_info())
            transfer_task = asyncio.create_task(self._client.get_transfer_metrics())
            keys_task = asyncio.create_task(self._client.get_access_keys())

            # Use gather with return_exceptions for resilience
            results = await asyncio.gather(
                server_task,
                transfer_task,
                keys_task,
                return_exceptions=True,
            )

            server_info, transfer_metrics, keys = results

            # Handle errors gracefully
            server_dict = (
                server_info.to_dict() if not isinstance(server_info, Exception) else {}
            )
            transfer_dict = (
                transfer_metrics.to_dict()
                if not isinstance(transfer_metrics, Exception)
                else {}
            )
            keys_list = keys if not isinstance(keys, Exception) else []

            # Try to get experimental metrics (optional)
            experimental_dict: dict[str, Any] = {}
            with suppress(Exception):
                exp_metrics = await self._client.get_experimental_metrics()
                experimental_dict = exp_metrics.to_dict()

            # Calculate total bytes
            total_bytes = transfer_dict.get("bytesTransferredByUserId", {})
            total_bytes_sum = (
                sum(total_bytes.values()) if isinstance(total_bytes, dict) else 0
            )

            timestamp = asyncio.get_event_loop().time()

            return MetricsSnapshot(
                timestamp=timestamp,
                server_info=server_dict,
                transfer_metrics=transfer_dict,
                experimental_metrics=experimental_dict,
                key_count=len(keys_list),
                total_bytes_transferred=total_bytes_sum,
            )

        except Exception as exc:
            _log_if_enabled(
                logging.ERROR,
                f"Failed to collect metrics snapshot: {exc}",
            )
            return None

    async def _collect_loop(self) -> None:
        """Main collection loop with error recovery."""
        consecutive_errors = 0
        max_consecutive_errors = 3

        while self._running and not self._shutdown_event.is_set():
            try:
                snapshot = await self._collect_single_snapshot()

                if snapshot is not None:
                    self._history.append(snapshot)
                    consecutive_errors = 0  # Reset error counter
                    _log_if_enabled(
                        logging.DEBUG,
                        f"Collected metrics snapshot (history size: {len(self._history)})",
                    )
                else:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        _log_if_enabled(
                            logging.WARNING,
                            f"Failed to collect metrics {consecutive_errors} times consecutively",
                        )
                        # Don't break, keep trying

                # Invalidate stats cache
                self._stats_cache = None

            except asyncio.CancelledError:
                _log_if_enabled(logging.INFO, "Metrics collection cancelled")
                break
            except Exception as exc:
                _log_if_enabled(
                    logging.ERROR,
                    f"Unexpected error in collection loop: {exc}",
                )
                consecutive_errors += 1

            # Wait for next collection
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self._interval,
                )
                break  # Shutdown signaled
            except TimeoutError:
                pass  # Normal timeout, continue loop

    async def start(self) -> None:
        """Start metrics collection.

        :raises RuntimeError: If already running
        """
        if self._running:
            msg = "Collector already running"
            raise RuntimeError(msg)

        self._running = True
        self._shutdown_event.clear()
        self._start_time = asyncio.get_event_loop().time()
        self._task = asyncio.create_task(self._collect_loop())

        _log_if_enabled(
            logging.INFO,
            f"Metrics collector started (interval={self._interval}s, max_history={self._max_history})",
        )

    async def stop(self) -> None:
        """Stop metrics collection gracefully."""
        if not self._running:
            return

        _log_if_enabled(logging.INFO, "Stopping metrics collector...")

        self._running = False
        self._shutdown_event.set()

        if self._task and not self._task.done():
            # Give task time to finish gracefully
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                _log_if_enabled(
                    logging.WARNING,
                    "Collection task did not finish gracefully, cancelling",
                )
                self._task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._task

        self._task = None
        _log_if_enabled(logging.INFO, "Metrics collector stopped")

    def get_snapshots(
        self,
        *,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int | None = None,
    ) -> list[MetricsSnapshot]:
        """Get metrics snapshots with optional filtering.

        :param start_time: Filter snapshots after this timestamp
        :param end_time: Filter snapshots before this timestamp
        :param limit: Maximum snapshots to return
        :return: List of snapshots
        """
        snapshots = list(self._history)

        # Apply time filters using binary search for efficiency
        if start_time is not None:
            # Find first snapshot >= start_time
            idx = bisect.bisect_left(
                [s.timestamp for s in snapshots],
                start_time,
            )
            snapshots = snapshots[idx:]

        if end_time is not None:
            # Find last snapshot <= end_time
            idx = bisect.bisect_right(
                [s.timestamp for s in snapshots],
                end_time,
            )
            snapshots = snapshots[:idx]

        if limit is not None and limit > 0:
            snapshots = snapshots[-limit:]

        return snapshots

    def get_latest_snapshot(self) -> MetricsSnapshot | None:
        """Get most recent snapshot.

        :return: Latest snapshot or None
        """
        return self._history[-1] if self._history else None

    def get_usage_stats(
        self,
        *,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> UsageStats:
        """Calculate usage statistics for period (with caching).

        :param start_time: Period start timestamp
        :param end_time: Period end timestamp
        :return: Usage statistics
        """
        # Check cache (only for full history queries)
        if start_time is None and end_time is None:
            current_time = asyncio.get_event_loop().time()
            cache_age = current_time - self._stats_cache_time

            if self._stats_cache is not None and cache_age < 5.0:
                return self._stats_cache

        snapshots = self.get_snapshots(start_time=start_time, end_time=end_time)

        if not snapshots:
            return UsageStats(
                period_start=0.0,
                period_end=0.0,
                snapshots_count=0,
                total_bytes_transferred=0,
                avg_bytes_per_snapshot=0.0,
                peak_bytes=0,
                active_keys=frozenset(),
            )

        # Calculate stats efficiently
        total_bytes = 0
        peak_bytes = 0
        active_keys_set: set[str] = set()

        for snapshot in snapshots:
            total_bytes += snapshot.total_bytes_transferred
            peak_bytes = max(peak_bytes, snapshot.total_bytes_transferred)

            # Extract active keys
            bytes_by_user = snapshot.transfer_metrics.get(
                "bytesTransferredByUserId", {}
            )
            if isinstance(bytes_by_user, dict):
                active_keys_set.update(k for k, v in bytes_by_user.items() if v > 0)

        avg_bytes = total_bytes / len(snapshots) if snapshots else 0.0

        stats = UsageStats(
            period_start=snapshots[0].timestamp,
            period_end=snapshots[-1].timestamp,
            snapshots_count=len(snapshots),
            total_bytes_transferred=total_bytes,
            avg_bytes_per_snapshot=avg_bytes,
            peak_bytes=peak_bytes,
            active_keys=frozenset(active_keys_set),
        )

        # Update cache for full history queries
        if start_time is None and end_time is None:
            self._stats_cache = stats
            self._stats_cache_time = asyncio.get_event_loop().time()

        return stats

    def export_prometheus(
        self,
        *,
        include_per_key: bool = False,
    ) -> str:
        """Export all metrics in Prometheus format (with caching).

        :param include_per_key: Include per-key metrics
        :return: Prometheus formatted metrics
        """
        latest = self.get_latest_snapshot()
        if latest is None:
            return ""

        # Use cache key based on parameters
        cache_key = f"full_{include_per_key}_{latest.timestamp}"

        base_metrics: list[tuple[str, float | int, str, str, dict[str, str] | None]] = [
            (
                "outline_keys_total",
                latest.key_count,
                "gauge",
                "Total number of access keys",
                None,
            ),
            (
                "outline_bytes_transferred_total",
                latest.total_bytes_transferred,
                "counter",
                "Total bytes transferred across all keys",
                None,
            ),
            (
                "outline_megabytes_transferred_total",
                latest.total_bytes_transferred / (1024**2),
                "counter",
                "Total megabytes transferred",
                None,
            ),
            (
                "outline_gigabytes_transferred_total",
                latest.total_bytes_transferred / (1024**3),
                "counter",
                "Total gigabytes transferred",
                None,
            ),
            (
                "outline_snapshots_collected_total",
                len(self._history),
                "counter",
                "Total snapshots collected",
                None,
            ),
            (
                "outline_collector_interval_seconds",
                self._interval,
                "gauge",
                "Metrics collection interval in seconds",
                None,
            ),
            (
                "outline_collector_uptime_seconds",
                self.uptime,
                "counter",
                "Collector uptime in seconds",
                None,
            ),
        ]

        # Add server info metrics if available
        if "metricsEnabled" in latest.server_info:
            metrics_enabled = latest.server_info["metricsEnabled"]
            base_metrics.append(
                (
                    "outline_metrics_enabled",
                    1 if metrics_enabled else 0,
                    "gauge",
                    "Whether metrics collection is enabled on server",
                    None,
                )
            )

        if "portForNewAccessKeys" in latest.server_info:
            port = latest.server_info["portForNewAccessKeys"]
            base_metrics.append(
                (
                    "outline_default_port",
                    port,
                    "gauge",
                    "Default port for new access keys",
                    None,
                )
            )

        # Add per-key metrics if requested
        if include_per_key and "bytesTransferredByUserId" in latest.transfer_metrics:
            bytes_by_user = latest.transfer_metrics["bytesTransferredByUserId"]
            if isinstance(bytes_by_user, dict):
                for key_id, bytes_transferred in bytes_by_user.items():
                    base_metrics.extend(
                        [
                            (
                                "outline_key_bytes_total",
                                bytes_transferred,
                                "counter",
                                "Total bytes transferred by specific key",
                                {"key_id": str(key_id)},
                            ),
                            (
                                "outline_key_megabytes_total",
                                bytes_transferred / (1024**2),
                                "counter",
                                "Total megabytes transferred by specific key",
                                {"key_id": str(key_id)},
                            ),
                        ]
                    )

        # Add experimental metrics if available
        if "server" in latest.experimental_metrics:
            server_exp = latest.experimental_metrics["server"]

            # Tunnel time
            if "tunnelTime" in server_exp and "seconds" in server_exp["tunnelTime"]:
                tunnel_seconds = server_exp["tunnelTime"]["seconds"]
                base_metrics.extend(
                    [
                        (
                            "outline_tunnel_time_seconds_total",
                            tunnel_seconds,
                            "counter",
                            "Total tunnel connection time in seconds",
                            None,
                        ),
                        (
                            "outline_tunnel_time_hours_total",
                            tunnel_seconds / 3600,
                            "counter",
                            "Total tunnel connection time in hours",
                            None,
                        ),
                    ]
                )

            # Bandwidth - current
            if "bandwidth" in server_exp:
                bandwidth = server_exp["bandwidth"]
                if "current" in bandwidth and "data" in bandwidth["current"]:
                    current_data = bandwidth["current"]["data"]
                    if "bytes" in current_data:
                        current_bw = current_data["bytes"]
                        base_metrics.append(
                            (
                                "outline_bandwidth_current_bytes",
                                current_bw,
                                "gauge",
                                "Current bandwidth usage in bytes",
                                None,
                            )
                        )

                # Bandwidth - peak
                if "peak" in bandwidth and "data" in bandwidth["peak"]:
                    peak_data = bandwidth["peak"]["data"]
                    if "bytes" in peak_data:
                        peak_bw = peak_data["bytes"]
                        base_metrics.append(
                            (
                                "outline_bandwidth_peak_bytes",
                                peak_bw,
                                "gauge",
                                "Peak bandwidth usage in bytes",
                                None,
                            )
                        )

            # Location metrics
            if "locations" in server_exp:
                locations = server_exp["locations"]
                if isinstance(locations, list):
                    for loc in locations:
                        if not isinstance(loc, dict):
                            continue

                        location = loc.get("location", "unknown")
                        loc_bytes = 0
                        loc_time = 0

                        if (
                            "dataTransferred" in loc
                            and "bytes" in loc["dataTransferred"]
                        ):
                            loc_bytes = loc["dataTransferred"]["bytes"]

                        if "tunnelTime" in loc and "seconds" in loc["tunnelTime"]:
                            loc_time = loc["tunnelTime"]["seconds"]

                        if loc_bytes > 0 or loc_time > 0:
                            base_metrics.extend(
                                [
                                    (
                                        "outline_location_bytes_total",
                                        loc_bytes,
                                        "counter",
                                        "Total bytes transferred by location",
                                        {"location": str(location)},
                                    ),
                                    (
                                        "outline_location_tunnel_seconds_total",
                                        loc_time,
                                        "counter",
                                        "Total tunnel time by location",
                                        {"location": str(location)},
                                    ),
                                ]
                            )

        return self._prometheus_exporter.format_metrics_batch(
            base_metrics,
            cache_key=cache_key,
        )

    def export_prometheus_summary(self) -> str:
        """Export summary metrics in Prometheus format (lightweight, cached).

        :return: Prometheus formatted summary metrics
        """
        latest = self.get_latest_snapshot()
        if latest is None:
            return ""

        stats = self.get_usage_stats()
        cache_key = f"summary_{latest.timestamp}"

        summary_metrics: list[
            tuple[str, float | int, str, str, dict[str, str] | None]
        ] = [
            (
                "outline_keys_total",
                latest.key_count,
                "gauge",
                "Total number of access keys",
                None,
            ),
            (
                "outline_bytes_transferred_total",
                latest.total_bytes_transferred,
                "counter",
                "Total bytes transferred",
                None,
            ),
            (
                "outline_bytes_per_second",
                stats.bytes_per_second,
                "gauge",
                "Average bytes per second",
                None,
            ),
            (
                "outline_active_keys_total",
                len(stats.active_keys),
                "gauge",
                "Number of active keys",
                None,
            ),
            (
                "outline_snapshots_total",
                len(self._history),
                "counter",
                "Total snapshots collected",
                None,
            ),
        ]

        return self._prometheus_exporter.format_metrics_batch(
            summary_metrics,
            cache_key=cache_key,
        )

    def clear_history(self) -> None:
        """Clear collected metrics history and caches."""
        self._history.clear()
        self._stats_cache = None
        self._prometheus_exporter.clear_cache()
        _log_if_enabled(logging.INFO, "Metrics history and caches cleared")

    @property
    def is_running(self) -> bool:
        """Check if collector is running.

        :return: True if running
        """
        return self._running

    @property
    def snapshots_count(self) -> int:
        """Get number of collected snapshots.

        :return: Snapshot count
        """
        return len(self._history)

    @property
    def uptime(self) -> float:
        """Get collector uptime in seconds.

        :return: Uptime in seconds
        """
        if not self._running or self._start_time == 0:
            return 0.0
        return asyncio.get_event_loop().time() - self._start_time

    async def __aenter__(self) -> Self:
        """Context manager entry.

        :return: Self
        """
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Context manager exit.

        :param exc_type: Exception type
        :param exc_val: Exception value
        :param exc_tb: Exception traceback
        """
        await self.stop()


__all__ = [
    "MetricsCollector",
    "MetricsSnapshot",
    "UsageStats",
]
