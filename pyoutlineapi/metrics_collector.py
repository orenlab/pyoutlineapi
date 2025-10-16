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
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sortedcontainers import SortedList

from .common_types import Constants

if TYPE_CHECKING:
    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)  # Python 3.10+
class MetricsSnapshot:
    """Metrics snapshot with size validation.

    SECURITY: Validates total size to prevent memory exhaustion.
    """

    timestamp: float
    server_info: dict[str, Any] = field(default_factory=dict)
    transfer_metrics: dict[str, Any] = field(default_factory=dict)
    experimental_metrics: dict[str, Any] = field(default_factory=dict)
    key_count: int = 0
    total_bytes_transferred: int = 0

    def __post_init__(self) -> None:
        """Validate snapshot size."""
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
        """Convert snapshot to dictionary."""
        return {
            "timestamp": self.timestamp,
            "server": self.server_info,
            "transfer": self.transfer_metrics,
            "experimental": self.experimental_metrics,
            "keys_count": self.key_count,
            "total_bytes": self.total_bytes_transferred,
        }


@dataclass(slots=True)
class UsageStats:
    """Usage statistics for a time period."""

    period_start: float
    period_end: float
    snapshots_count: int
    total_bytes_transferred: int
    avg_bytes_per_snapshot: float
    peak_bytes: int
    active_keys: set[str] = field(default_factory=set)

    @property
    def duration(self) -> float:
        """Get period duration in seconds."""
        return self.period_end - self.period_start

    @property
    def bytes_per_second(self) -> float:
        """Calculate average bytes per second."""
        if self.duration == 0:
            return 0.0
        return self.total_bytes_transferred / self.duration

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "duration": self.duration,
            "snapshots_count": self.snapshots_count,
            "total_bytes_transferred": self.total_bytes_transferred,
            "avg_bytes_per_snapshot": self.avg_bytes_per_snapshot,
            "peak_bytes": self.peak_bytes,
            "bytes_per_second": self.bytes_per_second,
            "active_keys_count": len(self.active_keys),
        }


class MetricsCollector:
    """Enhanced metrics collector with memory protection.

    IMPROVEMENTS:
    - SortedList for efficient time-based queries
    - Memory exhaustion protection
    - Size validation
    """

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        interval: float = 60.0,
        max_history: int = 1440,
    ) -> None:
        """Initialize metrics collector."""
        self._client = client
        self._interval = interval
        self._max_history = max_history

        # Use SortedList for efficient time-based queries
        self._history: SortedList[MetricsSnapshot] = SortedList(
            key=lambda s: s.timestamp
        )

        self._running = False
        self._task: asyncio.Task | None = None
        self._start_time = 0.0

    async def start(self) -> None:
        """Start periodic metrics collection."""
        if self._running:
            logger.warning("Metrics collector already running")
            return

        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._collection_loop())

        logger.info(f"Metrics collector started (interval: {self._interval}s)")

    async def stop(self) -> None:
        """Stop metrics collection."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Metrics collector stopped")

    async def _collection_loop(self) -> None:
        """Background collection loop."""
        while self._running:
            try:
                snapshot = await self.collect_snapshot()

                # Add to sorted list
                self._history.add(snapshot)

                # Trim old entries
                while len(self._history) > self._max_history:
                    self._history.pop(0)

                await asyncio.sleep(self._interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                await asyncio.sleep(self._interval)

    async def collect_snapshot(self) -> MetricsSnapshot:
        """Collect single metrics snapshot with size validation."""
        snapshot = MetricsSnapshot(timestamp=time.time())

        try:
            # Server info
            server = await self._client.get_server_info(as_json=True)
            snapshot.server_info = server

            # Key count
            keys = await self._client.get_access_keys(as_json=True)
            snapshot.key_count = len(keys.get("accessKeys", []))

            # Transfer metrics
            try:
                metrics_status = await self._client.get_metrics_status(as_json=True)
                if metrics_status.get("metricsEnabled"):
                    transfer = await self._client.get_transfer_metrics(as_json=True)
                    snapshot.transfer_metrics = transfer

                    bytes_by_user = transfer.get("bytesTransferredByUserId", {})
                    snapshot.total_bytes_transferred = sum(bytes_by_user.values())
            except Exception as e:
                logger.debug(f"Could not collect transfer metrics: {e}")

            # Experimental metrics
            try:
                experimental = await self._client.get_experimental_metrics(
                    "24h", as_json=True
                )
                snapshot.experimental_metrics = experimental
            except Exception as e:
                logger.debug(f"Could not collect experimental metrics: {e}")

        except Exception as e:
            logger.error(f"Error collecting snapshot: {e}")

        return snapshot

    def get_latest_snapshot(self) -> MetricsSnapshot | None:
        """Get most recent snapshot."""
        if not self._history:
            return None
        return self._history[-1]

    def get_snapshots_after(self, cutoff_time: float) -> list[MetricsSnapshot]:
        """Get snapshots after cutoff time.

        Uses binary search for O(log n) lookup.
        """
        if not self._history:
            return []

        # Find insertion point (binary search)
        idx = self._history.bisect_left(MetricsSnapshot(timestamp=cutoff_time))

        return list(self._history[idx:])

    def get_usage_stats(self, period_minutes: int | None = None) -> UsageStats:
        """Calculate usage statistics for a time period."""
        if not self._history:
            current_time = time.time()
            return UsageStats(
                period_start=current_time,
                period_end=current_time,
                snapshots_count=0,
                total_bytes_transferred=0,
                avg_bytes_per_snapshot=0.0,
                peak_bytes=0,
            )

        # Get snapshots in period
        if period_minutes:
            cutoff_time = time.time() - (period_minutes * 60)
            snapshots = self.get_snapshots_after(cutoff_time)
        else:
            snapshots = list(self._history)

        if not snapshots:
            current_time = time.time()
            return UsageStats(
                period_start=current_time,
                period_end=current_time,
                snapshots_count=0,
                total_bytes_transferred=0,
                avg_bytes_per_snapshot=0.0,
                peak_bytes=0,
            )

        # Calculate stats
        total_bytes = sum(s.total_bytes_transferred for s in snapshots)
        avg_bytes = total_bytes / len(snapshots)
        peak_bytes = max(s.total_bytes_transferred for s in snapshots)

        # Collect active keys
        active_keys = set()
        for snapshot in snapshots:
            if snapshot.transfer_metrics:
                bytes_by_user = snapshot.transfer_metrics.get(
                    "bytesTransferredByUserId", {}
                )
                active_keys.update(bytes_by_user.keys())

        return UsageStats(
            period_start=snapshots[0].timestamp,
            period_end=snapshots[-1].timestamp,
            snapshots_count=len(snapshots),
            total_bytes_transferred=total_bytes,
            avg_bytes_per_snapshot=avg_bytes,
            peak_bytes=peak_bytes,
            active_keys=active_keys,
        )

    def get_key_usage(
        self,
        key_id: str,
        period_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Get usage statistics for specific key."""
        # Get snapshots
        if period_minutes:
            cutoff_time = time.time() - (period_minutes * 60)
            snapshots = self.get_snapshots_after(cutoff_time)
        else:
            snapshots = list(self._history)

        # Collect key data
        total_bytes = 0
        data_points = []

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

        # Calculate stats
        duration = snapshots[-1].timestamp - snapshots[0].timestamp if snapshots else 0
        bytes_per_second = total_bytes / duration if duration > 0 else 0

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
        """Export all metrics to dictionary."""
        return {
            "collection_start": self._start_time,
            "collection_end": time.time(),
            "interval": self._interval,
            "snapshots_count": len(self._history),
            "snapshots": [s.to_dict() for s in self._history],
            "summary": self.get_usage_stats().to_dict() if self._history else {},
        }

    def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus format."""
        if not self._history:
            return ""

        latest = self._history[-1]
        stats = self.get_usage_stats()

        lines = [
            "# HELP outline_keys_count Number of access keys",
            "# TYPE outline_keys_count gauge",
            f"outline_keys_count {latest.key_count}",
            "",
            "# HELP outline_total_bytes_transferred Total bytes transferred",
            "# TYPE outline_total_bytes_transferred counter",
            f"outline_total_bytes_transferred {latest.total_bytes_transferred}",
            "",
            "# HELP outline_bytes_per_second Average bytes per second",
            "# TYPE outline_bytes_per_second gauge",
            f"outline_bytes_per_second {stats.bytes_per_second:.2f}",
            "",
            "# HELP outline_active_keys_count Number of active keys",
            "# TYPE outline_active_keys_count gauge",
            f"outline_active_keys_count {len(stats.active_keys)}",
        ]

        return "\n".join(lines)

    def clear_history(self) -> None:
        """Clear collected metrics history."""
        self._history.clear()
        logger.info("Metrics history cleared")

    @property
    def is_running(self) -> bool:
        """Check if collector is running."""
        return self._running

    @property
    def snapshots_count(self) -> int:
        """Get number of collected snapshots."""
        return len(self._history)

    async def __aenter__(self) -> MetricsCollector:
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        await self.stop()


__all__ = [
    "MetricsCollector",
    "MetricsSnapshot",
    "UsageStats",
]
