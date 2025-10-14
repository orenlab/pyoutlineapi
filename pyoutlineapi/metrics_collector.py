"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Advanced metrics collection (optional addon).

Provides periodic metrics collection, historical data storage,
and export capabilities for Outline VPN servers.

Usage:
    >>> from pyoutlineapi import AsyncOutlineClient
    >>> from pyoutlineapi.metrics_collector import MetricsCollector
    >>>
    >>> async with AsyncOutlineClient.from_env() as client:
    ...     collector = MetricsCollector(client, interval=60)
    ...     await collector.start()
    ...     await asyncio.sleep(300)  # Collect for 5 minutes
    ...     await collector.stop()
    ...     stats = collector.get_usage_stats()
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    """
    Snapshot of collected metrics at a point in time.

    Contains server information, transfer metrics, and key statistics.

    Attributes:
        timestamp: Snapshot timestamp (Unix time)
        server_info: Server information
        transfer_metrics: Transfer metrics by key
        experimental_metrics: Experimental server metrics
        key_count: Number of access keys
        total_bytes_transferred: Total bytes across all keys
    """

    timestamp: float
    server_info: dict[str, Any] = field(default_factory=dict)
    transfer_metrics: dict[str, Any] = field(default_factory=dict)
    experimental_metrics: dict[str, Any] = field(default_factory=dict)
    key_count: int = 0
    total_bytes_transferred: int = 0

    def to_dict(self) -> dict[str, Any]:
        """
        Convert snapshot to dictionary.

        Returns:
            dict: Snapshot as dictionary

        Example:
            >>> snapshot = await collector.collect_snapshot()
            >>> data = snapshot.to_dict()
            >>> print(f"Keys: {data['keys_count']}")
        """
        return {
            "timestamp": self.timestamp,
            "server": self.server_info,
            "transfer": self.transfer_metrics,
            "experimental": self.experimental_metrics,
            "keys_count": self.key_count,
            "total_bytes": self.total_bytes_transferred,
        }


@dataclass
class UsageStats:
    """
    Usage statistics for a time period.

    Calculates aggregate statistics from multiple snapshots.

    Attributes:
        period_start: Period start timestamp
        period_end: Period end timestamp
        snapshots_count: Number of snapshots in period
        total_bytes_transferred: Total bytes in period
        avg_bytes_per_snapshot: Average bytes per snapshot
        peak_bytes: Peak bytes in single snapshot
        active_keys: Set of active key IDs
    """

    period_start: float
    period_end: float
    snapshots_count: int
    total_bytes_transferred: int
    avg_bytes_per_snapshot: float
    peak_bytes: int
    active_keys: set[str] = field(default_factory=set)

    @property
    def duration(self) -> float:
        """
        Get period duration in seconds.

        Returns:
            float: Duration in seconds

        Example:
            >>> stats = collector.get_usage_stats()
            >>> print(f"Period: {stats.duration / 3600:.1f} hours")
        """
        return self.period_end - self.period_start

    @property
    def bytes_per_second(self) -> float:
        """
        Calculate average bytes per second.

        Returns:
            float: Bytes per second

        Example:
            >>> stats = collector.get_usage_stats()
            >>> print(f"Avg rate: {stats.bytes_per_second / 1024 / 1024:.2f} MB/s")
        """
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
    """
    Advanced metrics collection for Outline server.

    Features:
    - Periodic metrics collection with configurable interval
    - Historical data storage with size limits
    - Usage statistics calculation
    - Per-key usage tracking
    - Export to JSON and Prometheus formats

    Example:
        >>> from pyoutlineapi import AsyncOutlineClient
        >>> from pyoutlineapi.metrics_collector import MetricsCollector
        >>>
        >>> async with AsyncOutlineClient.from_env() as client:
        ...     # Create collector with 1-minute interval
        ...     collector = MetricsCollector(client, interval=60)
        ...
        ...     # Start collection
        ...     await collector.start()
        ...
        ...     # Let it run for a while
        ...     await asyncio.sleep(3600)  # 1 hour
        ...
        ...     # Stop and get stats
        ...     await collector.stop()
        ...     stats = collector.get_usage_stats()
        ...     print(f"Total bytes: {stats.total_bytes_transferred}")
        ...     print(f"Avg rate: {stats.bytes_per_second:.2f} B/s")
    """

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        interval: float = 60.0,
        max_history: int = 1440,  # 24 hours at 1min interval
    ) -> None:
        """
        Initialize metrics collector.

        Args:
            client: Outline client instance
            interval: Collection interval in seconds (default: 60)
            max_history: Maximum snapshots to keep (default: 1440 = 24h at 1min)

        Example:
            >>> collector = MetricsCollector(
            ...     client,
            ...     interval=30,      # Collect every 30 seconds
            ...     max_history=2880, # Keep 24 hours (at 30s interval)
            ... )
        """
        self._client = client
        self._interval = interval
        self._max_history = max_history

        self._history: Deque[MetricsSnapshot] = deque(maxlen=max_history)
        self._running = False
        self._task: asyncio.Task | None = None
        self._start_time = 0.0

    async def start(self) -> None:
        """
        Start periodic metrics collection.

        Begins background collection task that runs every interval seconds.

        Example:
            >>> collector = MetricsCollector(client, interval=30)
            >>> await collector.start()
            >>> # Metrics are now collected every 30 seconds
        """
        if self._running:
            logger.warning("Metrics collector already running")
            return

        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._collection_loop())

        logger.info(f"Metrics collector started (interval: {self._interval}s)")

    async def stop(self) -> None:
        """
        Stop metrics collection.

        Stops the background collection task gracefully.

        Example:
            >>> await collector.stop()
            >>> print(f"Collected {collector.snapshots_count} snapshots")
        """
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
                # Collect snapshot
                snapshot = await self.collect_snapshot()
                self._history.append(snapshot)

                # Wait for next interval
                await asyncio.sleep(self._interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                await asyncio.sleep(self._interval)

    async def collect_snapshot(self) -> MetricsSnapshot:
        """
        Collect single metrics snapshot.

        Gathers current server info, key count, and transfer metrics.

        Returns:
            MetricsSnapshot: Current metrics snapshot

        Example:
            >>> snapshot = await collector.collect_snapshot()
            >>> print(f"Keys: {snapshot.key_count}")
            >>> print(f"Total bytes: {snapshot.total_bytes_transferred}")
        """
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

                    # Calculate total bytes
                    bytes_by_user = transfer.get("bytesTransferredByUserId", {})
                    snapshot.total_bytes_transferred = sum(bytes_by_user.values())
            except Exception as e:
                logger.debug(f"Could not collect transfer metrics: {e}")

            # Experimental metrics (optional)
            try:
                experimental = await self._client.get_experimental_metrics(
                    "24h",
                    as_json=True,
                )
                snapshot.experimental_metrics = experimental
            except Exception as e:
                logger.debug(f"Could not collect experimental metrics: {e}")

        except Exception as e:
            logger.error(f"Error collecting snapshot: {e}")

        return snapshot

    def get_latest_snapshot(self) -> MetricsSnapshot | None:
        """
        Get most recent snapshot.

        Returns:
            MetricsSnapshot | None: Latest snapshot or None if no history

        Example:
            >>> latest = collector.get_latest_snapshot()
            >>> if latest:
            ...     print(f"Current keys: {latest.key_count}")
        """
        if not self._history:
            return None
        return self._history[-1]

    def get_usage_stats(
        self,
        period_minutes: int | None = None,
    ) -> UsageStats:
        """
        Calculate usage statistics for a time period.

        Args:
            period_minutes: Period in minutes (None = all history)

        Returns:
            UsageStats: Calculated usage statistics

        Example:
            >>> # Last hour stats
            >>> stats = collector.get_usage_stats(period_minutes=60)
            >>> print(f"Total bytes: {stats.total_bytes_transferred}")
            >>> print(f"Avg rate: {stats.bytes_per_second / 1024:.2f} KB/s")
            >>> print(f"Active keys: {len(stats.active_keys)}")
            >>>
            >>> # All-time stats
            >>> stats = collector.get_usage_stats()
        """
        if not self._history:
            return UsageStats(
                period_start=time.time(),
                period_end=time.time(),
                snapshots_count=0,
                total_bytes_transferred=0,
                avg_bytes_per_snapshot=0.0,
                peak_bytes=0,
            )

        # Filter by period
        current_time = time.time()
        if period_minutes:
            cutoff_time = current_time - (period_minutes * 60)
            snapshots = [s for s in self._history if s.timestamp >= cutoff_time]
        else:
            snapshots = list(self._history)

        if not snapshots:
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
                    "bytesTransferredByUserId",
                    {},
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
        """
        Get usage statistics for specific key.

        Args:
            key_id: Access key identifier
            period_minutes: Period in minutes (None = all history)

        Returns:
            dict: Key usage statistics

        Example:
            >>> usage = collector.get_key_usage("key1", period_minutes=60)
            >>> print(f"Total: {usage['total_bytes'] / 1024**2:.2f} MB")
            >>> print(f"Rate: {usage['bytes_per_second'] / 1024:.2f} KB/s")
        """
        # Filter snapshots by period
        current_time = time.time()
        if period_minutes:
            cutoff_time = current_time - (period_minutes * 60)
            snapshots = [s for s in self._history if s.timestamp >= cutoff_time]
        else:
            snapshots = list(self._history)

        # Collect key data
        total_bytes = 0
        data_points = []

        for snapshot in snapshots:
            if snapshot.transfer_metrics:
                bytes_by_user = snapshot.transfer_metrics.get(
                    "bytesTransferredByUserId",
                    {},
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
        """
        Export all collected metrics to dictionary.

        Returns:
            dict: All metrics and snapshots

        Example:
            >>> data = collector.export_to_dict()
            >>> import json
            >>> with open("metrics.json", "w") as f:
            ...     json.dump(data, f, indent=2)
        """
        return {
            "collection_start": self._start_time,
            "collection_end": time.time(),
            "interval": self._interval,
            "snapshots_count": len(self._history),
            "snapshots": [s.to_dict() for s in self._history],
            "summary": self.get_usage_stats().to_dict() if self._history else {},
        }

    def export_prometheus_format(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            str: Prometheus-formatted metrics

        Example:
            >>> metrics_text = collector.export_prometheus_format()
            >>> # Save to file for Prometheus scraping
            >>> with open("/var/metrics/outline.prom", "w") as f:
            ...     f.write(metrics_text)
        """
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
        """
        Clear collected metrics history.

        Example:
            >>> collector.clear_history()
            >>> print(f"Cleared, now {collector.snapshots_count} snapshots")
        """
        self._history.clear()
        logger.info("Metrics history cleared")

    @property
    def is_running(self) -> bool:
        """
        Check if collector is running.

        Returns:
            bool: True if collection is active
        """
        return self._running

    @property
    def snapshots_count(self) -> int:
        """
        Get number of collected snapshots.

        Returns:
            int: Number of snapshots in history
        """
        return len(self._history)

    async def __aenter__(self) -> MetricsCollector:
        """
        Context manager entry - start collection.

        Example:
            >>> async with MetricsCollector(client, interval=60) as collector:
            ...     await asyncio.sleep(300)  # Collect for 5 minutes
            ...     stats = collector.get_usage_stats()
        """
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - stop collection."""
        await self.stop()


__all__ = [
    "MetricsCollector",
    "MetricsSnapshot",
    "UsageStats",
]
