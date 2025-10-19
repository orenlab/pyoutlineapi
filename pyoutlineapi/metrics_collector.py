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
import logging
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from sortedcontainers import SortedList

from .common_types import Constants

if TYPE_CHECKING:
    from typing_extensions import Self

    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)

# Constants
_MIN_INTERVAL: Final[float] = 1.0
_MAX_INTERVAL: Final[float] = 3600.0
_MAX_HISTORY: Final[int] = 100_000


def _log_if_enabled(level: int, message: str) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    """
    if logger.isEnabledFor(level):
        logger.log(level, message)


@dataclass(slots=True, frozen=True)
class MetricsSnapshot:
    """Immutable metrics snapshot with size validation.

    Thread-safe due to immutability.
    """

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
            raise ValueError(
                f"Snapshot too large: {total_size / 1024 / 1024:.2f} MB "
                f"(max {Constants.MAX_SNAPSHOT_SIZE_MB} MB)"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary.

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


@dataclass(slots=True, frozen=True)
class UsageStats:
    """Immutable usage statistics for a time period.

    Provides comprehensive traffic analysis.
    """

    period_start: float
    period_end: float
    snapshots_count: int
    total_bytes_transferred: int
    avg_bytes_per_snapshot: float
    peak_bytes: int
    active_keys: frozenset[str] = field(default_factory=frozenset)

    @property
    def duration(self) -> float:
        """Get period duration in seconds.

        :return: Duration in seconds
        """
        return max(0.0, self.period_end - self.period_start)

    @property
    def bytes_per_second(self) -> float:
        """Calculate average bytes per second.

        :return: Bytes per second
        """
        duration = self.duration
        if duration == 0:
            return 0.0
        return self.total_bytes_transferred / duration

    @property
    def megabytes_transferred(self) -> float:
        """Get total in megabytes.

        :return: Total MB transferred
        """
        return self.total_bytes_transferred / (1024**2)

    @property
    def gigabytes_transferred(self) -> float:
        """Get total in gigabytes.

        :return: Total GB transferred
        """
        return self.total_bytes_transferred / (1024**3)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

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


class PrometheusExporter:
    """Helper class for Prometheus metrics export (DRY)."""

    __slots__ = ()

    @staticmethod
    def format_metric(
        name: str,
        value: float | int,
        metric_type: str = "gauge",
        help_text: str = "",
        labels: dict[str, str] | None = None,
    ) -> list[str]:
        """Format single Prometheus metric.

        :param name: Metric name
        :param value: Metric value
        :param metric_type: Metric type (gauge, counter, histogram, summary)
        :param help_text: Help text description
        :param labels: Optional labels dictionary
        :return: List of formatted metric lines
        """
        lines: list[str] = []

        if help_text:
            lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")

        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")

        return lines

    @staticmethod
    def format_metrics_batch(
        metrics: list[tuple[str, float | int, str, str, dict[str, str] | None]],
    ) -> str:
        """Format multiple metrics at once.

        :param metrics: List of (name, value, type, help, labels) tuples
        :return: Formatted Prometheus metrics string
        """
        all_lines: list[str] = []

        for name, value, metric_type, help_text, labels in metrics:
            metric_lines = PrometheusExporter.format_metric(
                name, value, metric_type, help_text, labels
            )
            all_lines.extend(metric_lines)
            all_lines.append("")  # Empty line between metrics

        return "\n".join(all_lines)


class MetricsCollector:
    """Enhanced metrics collector with memory protection and thread-safety.

    Features:
    - Automatic size validation
    - Memory-efficient sorted storage
    - Configurable history limits
    - Context manager support
    - Extended Prometheus export
    """

    __slots__ = (
        "_client",
        "_history",
        "_interval",
        "_max_history",
        "_prometheus_exporter",
        "_running",
        "_shutdown_lock",
        "_start_time",
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
        :param interval: Collection interval in seconds (1.0-3600.0)
        :param max_history: Maximum snapshots to keep (1-100000)
        :raises ValueError: If parameters are invalid
        """
        # Validate parameters
        if not _MIN_INTERVAL <= interval <= _MAX_INTERVAL:
            raise ValueError(
                f"interval must be between {_MIN_INTERVAL} and {_MAX_INTERVAL}"
            )

        if not 1 <= max_history <= _MAX_HISTORY:
            raise ValueError(f"max_history must be between 1 and {_MAX_HISTORY}")

        self._client = client
        self._interval = interval
        self._max_history = max_history

        # Sorted list for efficient time-based queries
        self._history: SortedList[MetricsSnapshot] = SortedList(
            key=lambda s: s.timestamp
        )

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._start_time = 0.0
        self._shutdown_lock = asyncio.Lock()
        self._prometheus_exporter = PrometheusExporter()

    async def start(self) -> None:
        """Start periodic metrics collection.

        :raises RuntimeError: If already running
        """
        if self._running:
            _log_if_enabled(logging.WARNING, "Metrics collector already running")
            raise RuntimeError("Metrics collector already running")

        self._running = True
        self._start_time = asyncio.get_event_loop().time()
        self._task = asyncio.create_task(self._collection_loop())

        _log_if_enabled(
            logging.INFO, f"Metrics collector started (interval: {self._interval}s)"
        )

    async def stop(self, *, timeout: float = 5.0) -> None:
        """Stop metrics collection gracefully.

        :param timeout: Maximum time to wait for collection task
        """
        async with self._shutdown_lock:
            if not self._running:
                return

            self._running = False

            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await asyncio.wait_for(self._task, timeout=timeout)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                finally:
                    self._task = None

            _log_if_enabled(logging.INFO, "Metrics collector stopped")

    async def _collection_loop(self) -> None:
        """Background collection loop with error handling."""
        while self._running:
            try:
                snapshot = await self.collect_snapshot()

                # Add snapshot and enforce size limit (optimized)
                self._history.add(snapshot)
                self._trim_history()

                await asyncio.sleep(self._interval)

            except asyncio.CancelledError:
                _log_if_enabled(logging.DEBUG, "Collection loop cancelled")
                break

            except Exception as e:
                _log_if_enabled(logging.ERROR, f"Error collecting metrics: {e}")
                await asyncio.sleep(self._interval)

    def _trim_history(self) -> None:
        """Trim history to max_history size (optimized).

        Uses efficient batch removal instead of pop(0) in loop.
        """
        if len(self._history) > self._max_history:
            excess = len(self._history) - self._max_history
            # Efficient batch removal using del with slice
            del self._history[:excess]

    async def collect_snapshot(self) -> MetricsSnapshot:
        """Collect single metrics snapshot with size validation.

        :return: Metrics snapshot
        :raises ValueError: If snapshot exceeds size limit
        """
        snapshot_data: dict[str, Any] = {"timestamp": asyncio.get_event_loop().time()}

        try:
            # Collect server info
            server = await self._client.get_server_info(as_json=True)
            snapshot_data["server_info"] = server

            # Collect access keys count
            keys = await self._client.get_access_keys(as_json=True)
            snapshot_data["key_count"] = len(keys.get("accessKeys", []))

            # Collect transfer metrics if enabled
            try:
                metrics_status = await self._client.get_metrics_status(as_json=True)
                if metrics_status.get("metricsEnabled"):
                    transfer = await self._client.get_transfer_metrics(as_json=True)
                    snapshot_data["transfer_metrics"] = transfer

                    bytes_by_user = transfer.get("bytesTransferredByUserId", {})
                    snapshot_data["total_bytes_transferred"] = sum(
                        bytes_by_user.values()
                    )
            except Exception as e:
                _log_if_enabled(
                    logging.DEBUG, f"Could not collect transfer metrics: {e}"
                )

            # Collect experimental metrics
            try:
                experimental = await self._client.get_experimental_metrics(
                    "24h", as_json=True
                )
                snapshot_data["experimental_metrics"] = experimental
            except Exception as e:
                _log_if_enabled(
                    logging.DEBUG, f"Could not collect experimental metrics: {e}"
                )

        except Exception as e:
            _log_if_enabled(logging.ERROR, f"Error collecting snapshot: {e}")

        return MetricsSnapshot(**snapshot_data)

    def get_latest_snapshot(self) -> MetricsSnapshot | None:
        """Get most recent snapshot.

        :return: Latest snapshot or None if no snapshots
        """
        if not self._history:
            return None
        return self._history[-1]

    def get_snapshots_after(self, cutoff_time: float) -> list[MetricsSnapshot]:
        """Get snapshots after cutoff time using binary search.

        :param cutoff_time: Cutoff timestamp
        :return: List of snapshots after cutoff
        """
        if not self._history:
            return []

        # Create dummy snapshot for binary search
        dummy = MetricsSnapshot(timestamp=cutoff_time)
        idx = self._history.bisect_left(dummy)

        return list(self._history[idx:])

    def get_usage_stats(self, period_minutes: int | None = None) -> UsageStats:
        """Calculate usage statistics for a time period.

        :param period_minutes: Period length in minutes, or None for all time
        :return: Usage statistics
        :raises ValueError: If period_minutes is negative
        """
        if period_minutes is not None and period_minutes < 0:
            raise ValueError("period_minutes must be non-negative")

        current_time = asyncio.get_event_loop().time()

        # Handle empty history
        if not self._history:
            return UsageStats(
                period_start=current_time,
                period_end=current_time,
                snapshots_count=0,
                total_bytes_transferred=0,
                avg_bytes_per_snapshot=0.0,
                peak_bytes=0,
                active_keys=frozenset(),
            )

        # Get snapshots for period
        if period_minutes:
            cutoff_time = current_time - (period_minutes * 60)
            snapshots = self.get_snapshots_after(cutoff_time)
        else:
            snapshots = list(self._history)

        # Handle no snapshots in period
        if not snapshots:
            return UsageStats(
                period_start=current_time,
                period_end=current_time,
                snapshots_count=0,
                total_bytes_transferred=0,
                avg_bytes_per_snapshot=0.0,
                peak_bytes=0,
                active_keys=frozenset(),
            )

        # Calculate statistics
        total_bytes = sum(s.total_bytes_transferred for s in snapshots)
        avg_bytes = total_bytes / len(snapshots)
        peak_bytes = max(s.total_bytes_transferred for s in snapshots)

        # Collect active keys
        active_keys_set: set[str] = set()
        for snapshot in snapshots:
            if snapshot.transfer_metrics:
                bytes_by_user = snapshot.transfer_metrics.get(
                    "bytesTransferredByUserId", {}
                )
                active_keys_set.update(bytes_by_user.keys())

        return UsageStats(
            period_start=snapshots[0].timestamp,
            period_end=snapshots[-1].timestamp,
            snapshots_count=len(snapshots),
            total_bytes_transferred=total_bytes,
            avg_bytes_per_snapshot=avg_bytes,
            peak_bytes=peak_bytes,
            active_keys=frozenset(active_keys_set),
        )

    def get_key_usage(
        self,
        key_id: str,
        period_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Get usage statistics for specific key.

        :param key_id: Access key ID
        :param period_minutes: Period length in minutes, or None for all time
        :return: Key usage statistics
        :raises ValueError: If key_id is empty or period_minutes is negative
        """
        if not key_id or not key_id.strip():
            raise ValueError("key_id cannot be empty")

        if period_minutes is not None and period_minutes < 0:
            raise ValueError("period_minutes must be non-negative")

        # Get snapshots for period
        if period_minutes:
            cutoff_time = asyncio.get_event_loop().time() - (period_minutes * 60)
            snapshots = self.get_snapshots_after(cutoff_time)
        else:
            snapshots = list(self._history)

        total_bytes = 0
        data_points: list[dict[str, Any]] = []

        for snapshot in snapshots:
            if snapshot.transfer_metrics:
                bytes_by_user = snapshot.transfer_metrics.get(
                    "bytesTransferredByUserId", {}
                )
                bytes_used = bytes_by_user.get(key_id, 0)
                total_bytes += bytes_used
                data_points.append(
                    {
                        "timestamp": snapshot.timestamp,
                        "bytes": bytes_used,
                    }
                )

        duration = (
            snapshots[-1].timestamp - snapshots[0].timestamp if snapshots else 0.0
        )
        bytes_per_second = total_bytes / duration if duration > 0 else 0.0

        return {
            "key_id": key_id,
            "total_bytes": total_bytes,
            "bytes_per_second": bytes_per_second,
            "data_points": data_points,
            "snapshots_count": len(snapshots),
            "period_start": snapshots[0].timestamp if snapshots else None,
            "period_end": snapshots[-1].timestamp if snapshots else None,
        }

    def export_to_dict(self) -> dict[str, Any]:
        """Export all metrics to dictionary.

        :return: Dictionary with all metrics data
        """
        return {
            "collection_start": self._start_time,
            "collection_end": asyncio.get_event_loop().time(),
            "interval": self._interval,
            "snapshots_count": len(self._history),
            "snapshots": [s.to_dict() for s in self._history],
            "summary": self.get_usage_stats().to_dict() if self._history else {},
        }

    def export_prometheus_format(self, *, include_per_key: bool = False) -> str:
        """Export metrics in Prometheus format with extended metrics.

        :param include_per_key: Include per-key metrics (can be verbose)
        :return: Prometheus formatted metrics
        """
        if not self._history:
            return ""

        latest = self._history[-1]
        stats = self.get_usage_stats()

        # Prepare base metrics
        base_metrics = [
            # Keys metrics
            (
                "outline_keys_total",
                latest.key_count,
                "gauge",
                "Total number of access keys",
                None,
            ),
            (
                "outline_active_keys_total",
                len(stats.active_keys),
                "gauge",
                "Number of active keys with traffic",
                None,
            ),
            # Traffic metrics
            (
                "outline_bytes_transferred_total",
                latest.total_bytes_transferred,
                "counter",
                "Total bytes transferred across all keys",
                None,
            ),
            (
                "outline_megabytes_transferred_total",
                stats.megabytes_transferred,
                "counter",
                "Total megabytes transferred across all keys",
                None,
            ),
            (
                "outline_gigabytes_transferred_total",
                stats.gigabytes_transferred,
                "counter",
                "Total gigabytes transferred across all keys",
                None,
            ),
            # Rate metrics
            (
                "outline_bytes_per_second",
                stats.bytes_per_second,
                "gauge",
                "Average bytes transferred per second",
                None,
            ),
            (
                "outline_megabytes_per_second",
                stats.bytes_per_second / (1024**2),
                "gauge",
                "Average megabytes transferred per second",
                None,
            ),
            # Peak metrics
            (
                "outline_peak_bytes",
                stats.peak_bytes,
                "gauge",
                "Peak bytes transferred in single snapshot",
                None,
            ),
            # Collection metrics
            (
                "outline_snapshots_total",
                len(self._history),
                "counter",
                "Total number of collected snapshots",
                None,
            ),
            (
                "outline_collection_interval_seconds",
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
        if latest.server_info:
            server = latest.server_info
            if "metricsEnabled" in server:
                base_metrics.append(
                    (
                        "outline_metrics_enabled",
                        1 if server["metricsEnabled"] else 0,
                        "gauge",
                        "Whether metrics collection is enabled on server",
                        None,
                    )
                )
            if "portForNewAccessKeys" in server:
                base_metrics.append(
                    (
                        "outline_default_port",
                        server["portForNewAccessKeys"],
                        "gauge",
                        "Default port for new access keys",
                        None,
                    )
                )

        # Add per-key metrics if requested
        if include_per_key and latest.transfer_metrics:
            bytes_by_user = latest.transfer_metrics.get("bytesTransferredByUserId", {})
            for key_id, bytes_transferred in bytes_by_user.items():
                base_metrics.extend(
                    [
                        (
                            "outline_key_bytes_total",
                            bytes_transferred,
                            "counter",
                            "Total bytes transferred by specific key",
                            {"key_id": key_id},
                        ),
                        (
                            "outline_key_megabytes_total",
                            bytes_transferred / (1024**2),
                            "counter",
                            "Total megabytes transferred by specific key",
                            {"key_id": key_id},
                        ),
                    ]
                )

        # Add experimental metrics if available
        if latest.experimental_metrics:
            exp = latest.experimental_metrics
            if "server" in exp:
                server_exp = exp["server"]

                # Tunnel time
                if "tunnelTime" in server_exp:
                    tunnel_seconds = server_exp["tunnelTime"].get("seconds", 0)
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

                # Bandwidth
                if "bandwidth" in server_exp:
                    bw = server_exp["bandwidth"]
                    if "current" in bw and "data" in bw["current"]:
                        current_bw = bw["current"]["data"].get("bytes", 0)
                        base_metrics.append(
                            (
                                "outline_bandwidth_current_bytes",
                                current_bw,
                                "gauge",
                                "Current bandwidth usage in bytes",
                                None,
                            )
                        )
                    if "peak" in bw and "data" in bw["peak"]:
                        peak_bw = bw["peak"]["data"].get("bytes", 0)
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
                    for loc in locations:
                        location = loc.get("location", "unknown")
                        loc_bytes = loc.get("dataTransferred", {}).get("bytes", 0)
                        loc_time = loc.get("tunnelTime", {}).get("seconds", 0)

                        base_metrics.extend(
                            [
                                (
                                    "outline_location_bytes_total",
                                    loc_bytes,
                                    "counter",
                                    "Total bytes transferred by location",
                                    {"location": location},
                                ),
                                (
                                    "outline_location_tunnel_seconds_total",
                                    loc_time,
                                    "counter",
                                    "Total tunnel time by location",
                                    {"location": location},
                                ),
                            ]
                        )

        return self._prometheus_exporter.format_metrics_batch(base_metrics)

    def export_prometheus_summary(self) -> str:
        """Export summary metrics in Prometheus format (lightweight).

        :return: Prometheus formatted summary metrics
        """
        if not self._history:
            return ""

        latest = self._history[-1]
        stats = self.get_usage_stats()

        summary_metrics = [
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

        return self._prometheus_exporter.format_metrics_batch(summary_metrics)

    def clear_history(self) -> None:
        """Clear collected metrics history."""
        self._history.clear()
        _log_if_enabled(logging.INFO, "Metrics history cleared")

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
