"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Advanced health monitoring (optional addon).

Provides comprehensive health checking and performance monitoring
for Outline VPN servers with custom check support.

Usage:
    >>> from pyoutlineapi import AsyncOutlineClient
    >>> from pyoutlineapi.health_monitoring import HealthMonitor
    >>>
    >>> async with AsyncOutlineClient.from_env() as client:
    ...     monitor = HealthMonitor(client)
    ...     health = await monitor.comprehensive_check()
    ...     print(f"Healthy: {health.healthy}")
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """
    Health check result with detailed status information.

    Contains overall health status, individual check results,
    and performance metrics.

    Attributes:
        healthy: Overall health status
        timestamp: Check timestamp (Unix time)
        checks: Individual check results by name
        metrics: Performance metrics by name
    """

    healthy: bool
    timestamp: float
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def failed_checks(self) -> list[str]:
        """
        Get list of failed check names.

        Returns:
            list[str]: Names of checks that failed

        Example:
            >>> health = await monitor.comprehensive_check()
            >>> if health.failed_checks:
            ...     print(f"Failed checks: {', '.join(health.failed_checks)}")
        """
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") != "healthy"
        ]

    @property
    def is_degraded(self) -> bool:
        """
        Check if service is degraded (partially working).

        Returns:
            bool: True if any checks are degraded

        Example:
            >>> health = await monitor.comprehensive_check()
            >>> if health.is_degraded:
            ...     print("⚠️ Service is degraded but operational")
        """
        return any(
            result.get("status") == "degraded" for result in self.checks.values()
        )


@dataclass
class PerformanceMetrics:
    """
    Performance tracking metrics.

    Tracks request statistics and uptime for monitoring.

    Attributes:
        total_requests: Total number of requests made
        successful_requests: Number of successful requests
        failed_requests: Number of failed requests
        avg_response_time: Average response time in seconds
        start_time: Monitoring start timestamp
    """

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    start_time: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        """
        Calculate success rate.

        Returns:
            float: Success rate (0.0 to 1.0)

        Example:
            >>> metrics = monitor.get_metrics()
            >>> print(f"Success rate: {metrics['success_rate']:.2%}")
        """
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def uptime(self) -> float:
        """
        Get uptime in seconds.

        Returns:
            float: Uptime since monitoring started

        Example:
            >>> metrics = monitor.get_metrics()
            >>> print(f"Uptime: {metrics['uptime'] / 3600:.1f} hours")
        """
        return time.time() - self.start_time


class HealthMonitor:
    """
    Advanced health monitoring for Outline client.

    Features:
    - Comprehensive health checks (connectivity, circuit breaker, performance)
    - Performance tracking and metrics
    - Circuit breaker awareness
    - Custom check registration
    - Result caching for efficiency

    Example:
        >>> from pyoutlineapi import AsyncOutlineClient
        >>> from pyoutlineapi.health_monitoring import HealthMonitor
        >>>
        >>> async with AsyncOutlineClient.from_env() as client:
        ...     monitor = HealthMonitor(client)
        ...
        ...     # Quick check
        ...     if await monitor.quick_check():
        ...         print("✅ Service reachable")
        ...
        ...     # Comprehensive check
        ...     health = await monitor.comprehensive_check()
        ...     print(f"Healthy: {health.healthy}")
        ...     print(f"Degraded: {health.is_degraded}")
        ...     for name in health.failed_checks:
        ...         print(f"❌ Failed: {name}")
    """

    def __init__(self, client: AsyncOutlineClient) -> None:
        """
        Initialize health monitor.

        Args:
            client: Outline client instance

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     monitor = HealthMonitor(client)
        """
        self._client = client
        self._metrics = PerformanceMetrics()
        self._custom_checks: dict[str, Any] = {}
        self._last_check_time = 0.0
        self._cached_result: HealthStatus | None = None
        self._cache_ttl = 30.0  # Cache for 30 seconds

    async def quick_check(self) -> bool:
        """
        Quick health check - connectivity only.

        Tests if the service is reachable by fetching server info.

        Returns:
            bool: True if service is reachable

        Example:
            >>> monitor = HealthMonitor(client)
            >>> if await monitor.quick_check():
            ...     print("Service is up")
            ... else:
            ...     print("Service is down")
        """
        try:
            await self._client.get_server_info()
            return True
        except Exception as e:
            logger.debug(f"Quick health check failed: {e}")
            return False

    async def comprehensive_check(
        self,
        *,
        use_cache: bool = True,
    ) -> HealthStatus:
        """
        Comprehensive health check with all subsystems.

        Checks:
        - Connectivity (can reach API)
        - Circuit breaker status
        - Performance metrics
        - Custom checks (if registered)

        Args:
            use_cache: Use cached result if recent (default: True)

        Returns:
            HealthStatus: Detailed health status

        Example:
            >>> health = await monitor.comprehensive_check()
            >>> if not health.healthy:
            ...     print("❌ Service unhealthy")
            ...     for check in health.failed_checks:
            ...         result = health.checks[check]
            ...         print(f"  {check}: {result['message']}")
            ...
            >>> if health.is_degraded:
            ...     print("⚠️ Service degraded")
        """
        # Check cache
        current_time = time.time()
        if (
            use_cache
            and self._cached_result
            and current_time - self._last_check_time < self._cache_ttl
        ):
            return self._cached_result

        status = HealthStatus(
            healthy=True,
            timestamp=current_time,
        )

        # Check 1: Connectivity
        await self._check_connectivity(status)

        # Check 2: Circuit breaker
        await self._check_circuit_breaker(status)

        # Check 3: Performance
        await self._check_performance(status)

        # Check 4: Custom checks
        await self._run_custom_checks(status)

        # Update cache
        self._cached_result = status
        self._last_check_time = current_time

        return status

    async def _check_connectivity(self, status: HealthStatus) -> None:
        """Check basic connectivity."""
        try:
            start = time.time()
            await self._client.get_server_info()
            duration = time.time() - start

            status.checks["connectivity"] = {
                "status": "healthy",
                "message": "API accessible",
                "response_time": duration,
            }
            status.metrics["connectivity_time"] = duration

        except Exception as e:
            status.healthy = False
            status.checks["connectivity"] = {
                "status": "unhealthy",
                "message": f"API unreachable: {e}",
            }

    async def _check_circuit_breaker(self, status: HealthStatus) -> None:
        """Check circuit breaker status."""
        metrics = self._client.get_circuit_metrics()

        if metrics is None:
            # Circuit breaker not enabled
            status.checks["circuit_breaker"] = {
                "status": "disabled",
                "message": "Circuit breaker not enabled",
            }
            return

        cb_state = metrics["state"]
        success_rate = metrics["success_rate"]

        if cb_state == "OPEN":
            status.healthy = False
            cb_status = "unhealthy"
        elif success_rate < 0.5:
            cb_status = "degraded"
        else:
            cb_status = "healthy"

        status.checks["circuit_breaker"] = {
            "status": cb_status,
            "state": cb_state,
            "success_rate": success_rate,
            "message": f"Circuit {cb_state.lower()}, success rate: {success_rate:.1%}",
        }

        status.metrics["circuit_success_rate"] = success_rate

    async def _check_performance(self, status: HealthStatus) -> None:
        """Check performance metrics."""
        success_rate = self._metrics.success_rate

        if success_rate > 0.9:
            perf_status = "healthy"
        elif success_rate > 0.5:
            perf_status = "degraded"
        else:
            perf_status = "unhealthy"
            status.healthy = False

        status.checks["performance"] = {
            "status": perf_status,
            "success_rate": success_rate,
            "total_requests": self._metrics.total_requests,
            "avg_response_time": self._metrics.avg_response_time,
            "uptime": self._metrics.uptime,
            "message": f"Success rate: {success_rate:.1%}",
        }

        status.metrics["success_rate"] = success_rate
        status.metrics["avg_response_time"] = self._metrics.avg_response_time

    async def _run_custom_checks(self, status: HealthStatus) -> None:
        """Run registered custom checks."""
        for name, check_func in self._custom_checks.items():
            try:
                result = await check_func(self._client)
                status.checks[name] = result

                # Update overall health
                if result.get("status") == "unhealthy":
                    status.healthy = False

            except Exception as e:
                status.checks[name] = {
                    "status": "error",
                    "message": f"Check failed: {e}",
                }

    def add_custom_check(
        self,
        name: str,
        check_func: Any,
    ) -> None:
        """
        Register custom health check function.

        Args:
            name: Unique check name
            check_func: Async function that takes client and returns check result dict

        Example:
            >>> async def check_keys_count(client):
            ...     keys = await client.get_access_keys()
            ...     count = keys.count
            ...     return {
            ...         "status": "healthy" if count > 0 else "warning",
            ...         "keys_count": count,
            ...         "message": f"{count} keys configured",
            ...     }
            >>>
            >>> monitor = HealthMonitor(client)
            >>> monitor.add_custom_check("keys_count", check_keys_count)
            >>> health = await monitor.comprehensive_check()
            >>> print(health.checks["keys_count"])
        """
        self._custom_checks[name] = check_func

    def remove_custom_check(self, name: str) -> None:
        """
        Remove custom health check.

        Args:
            name: Check name to remove

        Example:
            >>> monitor.remove_custom_check("keys_count")
        """
        self._custom_checks.pop(name, None)

    def record_request(self, success: bool, duration: float) -> None:
        """
        Record request result for performance metrics.

        Args:
            success: Whether request succeeded
            duration: Request duration in seconds

        Example:
            >>> import time
            >>> start = time.time()
            >>> try:
            ...     await client.get_server_info()
            ...     monitor.record_request(True, time.time() - start)
            ... except Exception:
            ...     monitor.record_request(False, time.time() - start)
        """
        self._metrics.total_requests += 1

        if success:
            self._metrics.successful_requests += 1
        else:
            self._metrics.failed_requests += 1

        # Update avg response time (exponential moving average)
        alpha = 0.1
        if self._metrics.avg_response_time == 0:
            self._metrics.avg_response_time = duration
        else:
            self._metrics.avg_response_time = (
                alpha * duration + (1 - alpha) * self._metrics.avg_response_time
            )

    def get_metrics(self) -> dict[str, Any]:
        """
        Get performance metrics.

        Returns:
            dict: Performance metrics dictionary

        Example:
            >>> metrics = monitor.get_metrics()
            >>> print(f"Total requests: {metrics['total_requests']}")
            >>> print(f"Success rate: {metrics['success_rate']:.2%}")
            >>> print(f"Avg response: {metrics['avg_response_time']:.3f}s")
            >>> print(f"Uptime: {metrics['uptime'] / 3600:.1f}h")
        """
        return {
            "total_requests": self._metrics.total_requests,
            "successful_requests": self._metrics.successful_requests,
            "failed_requests": self._metrics.failed_requests,
            "success_rate": self._metrics.success_rate,
            "avg_response_time": self._metrics.avg_response_time,
            "uptime": self._metrics.uptime,
        }

    async def wait_for_healthy(
        self,
        timeout: float = 60.0,
        check_interval: float = 5.0,
    ) -> bool:
        """
        Wait for service to become healthy.

        Polls the service until it becomes healthy or timeout is reached.

        Args:
            timeout: Maximum wait time in seconds (default: 60.0)
            check_interval: Time between checks in seconds (default: 5.0)

        Returns:
            bool: True if healthy within timeout, False otherwise

        Example:
            >>> monitor = HealthMonitor(client)
            >>> if await monitor.wait_for_healthy(timeout=120):
            ...     print("✅ Service is healthy!")
            ... else:
            ...     print("❌ Timeout waiting for healthy state")
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                if await self.quick_check():
                    return True
            except Exception as e:
                logger.debug(f"Health check failed: {e}")

            await asyncio.sleep(check_interval)

        return False


__all__ = [
    "HealthMonitor",
    "HealthStatus",
    "PerformanceMetrics",
]
