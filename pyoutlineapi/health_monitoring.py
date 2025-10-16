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
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HealthStatus:
    """Health check result with enhanced tracking.

    IMPROVEMENTS:
    - Slots for memory efficiency
    - Better categorization
    """

    healthy: bool
    timestamp: float
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def failed_checks(self) -> list[str]:
        """Get list of failed check names."""
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") != "healthy"
        ]

    @property
    def is_degraded(self) -> bool:
        """Check if service is degraded."""
        return any(
            result.get("status") == "degraded" for result in self.checks.values()
        )

    @property
    def warning_checks(self) -> list[str]:
        """Get list of warning check names."""
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") == "warning"
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "degraded": self.is_degraded,
            "timestamp": self.timestamp,
            "checks": self.checks,
            "metrics": self.metrics,
            "failed_checks": self.failed_checks,
            "warning_checks": self.warning_checks,
        }


@dataclass(slots=True)
class PerformanceMetrics:
    """Performance tracking metrics.

    IMPROVEMENTS:
    - Slots for memory efficiency
    """

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    start_time: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def uptime(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self.start_time


class HealthMonitor:
    """Enhanced health monitoring.

    IMPROVEMENTS:
    - Better caching strategy
    - Enhanced custom checks
    - Configurable cache TTL
    """

    __slots__ = (
        "_cache_ttl",
        "_cached_result",
        "_client",
        "_custom_checks",
        "_last_check_time",
        "_metrics",
    )

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        cache_ttl: float = 30.0,
    ) -> None:
        """Initialize health monitor with configurable cache."""
        self._client = client
        self._metrics = PerformanceMetrics()
        self._custom_checks: dict[str, Any] = {}
        self._last_check_time = 0.0
        self._cached_result: HealthStatus | None = None
        self._cache_ttl = cache_ttl

    async def quick_check(self) -> bool:
        """Quick health check - connectivity only."""
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
        force_refresh: bool = False,
    ) -> HealthStatus:
        """Comprehensive health check with enhanced caching.

        IMPROVEMENTS:
        - force_refresh option
        - Better cache invalidation
        """
        current_time = time.time()

        # Check cache
        if (
            use_cache
            and not force_refresh
            and self._cached_result
            and current_time - self._last_check_time < self._cache_ttl
        ):
            return self._cached_result

        status = HealthStatus(
            healthy=True,
            timestamp=current_time,
        )

        # Run all checks
        await self._check_connectivity(status)
        await self._check_circuit_breaker(status)
        await self._check_performance(status)
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

            # Determine health based on response time
            if duration < 1.0:
                check_status = "healthy"
            elif duration < 3.0:
                check_status = "warning"
            else:
                check_status = "degraded"

            status.checks["connectivity"] = {
                "status": check_status,
                "message": f"API accessible ({duration:.2f}s)",
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
            status.checks["circuit_breaker"] = {
                "status": "disabled",
                "message": "Circuit breaker not enabled",
            }
            return

        cb_state = metrics["state"]
        success_rate = metrics["success_rate"]

        # Determine health based on state and success rate
        if cb_state == "OPEN":
            status.healthy = False
            cb_status = "unhealthy"
        elif cb_state == "HALF_OPEN":
            cb_status = "warning"
        elif success_rate < 0.5:
            cb_status = "degraded"
        elif success_rate < 0.9:
            cb_status = "warning"
        else:
            cb_status = "healthy"

        status.checks["circuit_breaker"] = {
            "status": cb_status,
            "state": cb_state,
            "success_rate": success_rate,
            "message": f"Circuit {cb_state.lower()}, {success_rate:.1%} success",
        }

        status.metrics["circuit_success_rate"] = success_rate

    async def _check_performance(self, status: HealthStatus) -> None:
        """Check performance metrics."""
        success_rate = self._metrics.success_rate
        avg_time = self._metrics.avg_response_time

        # Determine health
        if success_rate > 0.95 and avg_time < 1.0:
            perf_status = "healthy"
        elif success_rate > 0.9 and avg_time < 2.0:
            perf_status = "warning"
        elif success_rate > 0.7:
            perf_status = "degraded"
        else:
            perf_status = "unhealthy"
            status.healthy = False

        status.checks["performance"] = {
            "status": perf_status,
            "success_rate": success_rate,
            "total_requests": self._metrics.total_requests,
            "avg_response_time": avg_time,
            "uptime": self._metrics.uptime,
            "message": f"{success_rate:.1%} success, {avg_time:.2f}s avg",
        }

        status.metrics["success_rate"] = success_rate
        status.metrics["avg_response_time"] = avg_time

    async def _run_custom_checks(self, status: HealthStatus) -> None:
        """Run registered custom checks."""
        for name, check_func in self._custom_checks.items():
            try:
                result = await check_func(self._client)
                status.checks[name] = result

                if result.get("status") == "unhealthy":
                    status.healthy = False

            except Exception as e:
                logger.error(f"Custom check '{name}' failed: {e}")
                status.checks[name] = {
                    "status": "error",
                    "message": f"Check failed: {e}",
                }

    def add_custom_check(self, name: str, check_func: Any) -> None:
        """Register custom health check function.

        IMPROVEMENTS:
        - Validation of check name
        """
        if not name or not name.strip():
            raise ValueError("Check name cannot be empty")

        if not callable(check_func):
            raise ValueError("Check function must be callable")

        self._custom_checks[name] = check_func
        logger.debug(f"Registered custom check: {name}")

    def remove_custom_check(self, name: str) -> None:
        """Remove custom health check."""
        self._custom_checks.pop(name, None)
        logger.debug(f"Removed custom check: {name}")

    def clear_custom_checks(self) -> None:
        """Clear all custom checks."""
        self._custom_checks.clear()
        logger.debug("Cleared all custom checks")

    def record_request(self, success: bool, duration: float) -> None:
        """Record request result for performance metrics."""
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
        """Get performance metrics."""
        return {
            "total_requests": self._metrics.total_requests,
            "successful_requests": self._metrics.successful_requests,
            "failed_requests": self._metrics.failed_requests,
            "success_rate": self._metrics.success_rate,
            "avg_response_time": self._metrics.avg_response_time,
            "uptime": self._metrics.uptime,
        }

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self._metrics = PerformanceMetrics()
        logger.debug("Reset performance metrics")

    def invalidate_cache(self) -> None:
        """Manually invalidate health check cache."""
        self._cached_result = None
        self._last_check_time = 0.0

    async def wait_for_healthy(
        self,
        timeout: float = 60.0,
        check_interval: float = 5.0,
    ) -> bool:
        """Wait for service to become healthy."""
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
