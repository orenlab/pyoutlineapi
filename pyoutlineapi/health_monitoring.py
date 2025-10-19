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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)

# Constants
_MIN_CACHE_TTL: Final[float] = 1.0
_MAX_CACHE_TTL: Final[float] = 300.0
_ALPHA: Final[float] = 0.1  # EMA smoothing factor

# Response time thresholds
_THRESHOLD_HEALTHY: Final[float] = 1.0
_THRESHOLD_WARNING: Final[float] = 3.0


def _log_if_enabled(level: int, message: str) -> None:
    """Centralized logging with level check.

    :param level: Logging level
    :param message: Log message
    """
    if logger.isEnabledFor(level):
        logger.log(level, message)


@dataclass(slots=True, frozen=True)
class HealthStatus:
    """Immutable health check result with enhanced tracking.

    Thread-safe due to immutability.
    """

    healthy: bool
    timestamp: float
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def failed_checks(self) -> list[str]:
        """Get list of failed check names.

        :return: List of failed check names
        """
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") == "unhealthy"
        ]

    @property
    def is_degraded(self) -> bool:
        """Check if service is degraded.

        :return: True if any check is degraded
        """
        return any(
            result.get("status") == "degraded" for result in self.checks.values()
        )

    @property
    def warning_checks(self) -> list[str]:
        """Get list of warning check names.

        :return: List of warning check names
        """
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") == "warning"
        ]

    @property
    def total_checks(self) -> int:
        """Get total number of checks performed.

        :return: Total check count
        """
        return len(self.checks)

    @property
    def passed_checks(self) -> int:
        """Get number of passed checks.

        :return: Passed check count
        """
        return sum(
            1 for result in self.checks.values() if result.get("status") == "healthy"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        :return: Dictionary representation
        """
        return {
            "healthy": self.healthy,
            "degraded": self.is_degraded,
            "timestamp": self.timestamp,
            "checks": self.checks,
            "metrics": self.metrics,
            "failed_checks": self.failed_checks,
            "warning_checks": self.warning_checks,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
        }


@dataclass(slots=True)
class PerformanceMetrics:
    """Performance tracking metrics with EMA smoothing."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    start_time: float = field(default_factory=lambda: asyncio.get_event_loop().time())

    @property
    def success_rate(self) -> float:
        """Calculate success rate.

        :return: Success rate as decimal (0.0 to 1.0)
        """
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate.

        :return: Failure rate as decimal (0.0 to 1.0)
        """
        return 1.0 - self.success_rate

    @property
    def uptime(self) -> float:
        """Get uptime in seconds.

        :return: Uptime in seconds
        """
        return asyncio.get_event_loop().time() - self.start_time


class HealthCheckHelper:
    """Helper class for health check operations (DRY)."""

    __slots__ = ()

    @staticmethod
    def determine_status_by_time(duration: float) -> str:
        """Determine health status based on response time.

        :param duration: Response time in seconds
        :return: Status string
        """
        if duration < _THRESHOLD_HEALTHY:
            return "healthy"
        elif duration < _THRESHOLD_WARNING:
            return "warning"
        else:
            return "degraded"

    @staticmethod
    def determine_circuit_status(cb_state: str, success_rate: float) -> str:
        """Determine circuit breaker health status.

        :param cb_state: Circuit breaker state name
        :param success_rate: Success rate (0.0 to 1.0)
        :return: Status string
        """
        if cb_state == "OPEN":
            return "unhealthy"
        elif cb_state == "HALF_OPEN":
            return "warning"
        elif success_rate < 0.5:
            return "degraded"
        elif success_rate < 0.9:
            return "warning"
        else:
            return "healthy"

    @staticmethod
    def determine_performance_status(success_rate: float, avg_time: float) -> str:
        """Determine performance health status.

        :param success_rate: Success rate (0.0 to 1.0)
        :param avg_time: Average response time in seconds
        :return: Status string
        """
        if success_rate > 0.95 and avg_time < 1.0:
            return "healthy"
        elif success_rate > 0.9 and avg_time < 2.0:
            return "warning"
        elif success_rate > 0.7:
            return "degraded"
        else:
            return "unhealthy"


class HealthMonitor:
    """Enhanced health monitoring with caching and custom checks.

    Features:
    - Configurable caching
    - Custom check registration
    - Performance metrics tracking
    - EMA smoothing for response times
    - Wait for healthy support
    """

    __slots__ = (
        "_cache_ttl",
        "_cached_result",
        "_client",
        "_custom_checks",
        "_helper",
        "_last_check_time",
        "_metrics",
    )

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        cache_ttl: float = 30.0,
    ) -> None:
        """Initialize health monitor.

        :param client: AsyncOutlineClient instance
        :param cache_ttl: Cache time-to-live in seconds (1.0-300.0)
        :raises ValueError: If cache_ttl is invalid
        """
        if not _MIN_CACHE_TTL <= cache_ttl <= _MAX_CACHE_TTL:
            raise ValueError(
                f"cache_ttl must be between {_MIN_CACHE_TTL} and {_MAX_CACHE_TTL}"
            )

        self._client = client
        self._metrics = PerformanceMetrics()
        self._custom_checks: dict[
            str, Callable[[AsyncOutlineClient], Coroutine[Any, Any, dict[str, Any]]]
        ] = {}
        self._last_check_time = 0.0
        self._cached_result: HealthStatus | None = None
        self._cache_ttl = cache_ttl
        self._helper = HealthCheckHelper()

    async def quick_check(self) -> bool:
        """Quick health check - connectivity only.

        :return: True if server is accessible
        """
        try:
            await self._client.get_server_info()
            return True
        except Exception as e:
            _log_if_enabled(logging.DEBUG, f"Quick health check failed: {e}")
            return False

    async def comprehensive_check(
        self,
        *,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> HealthStatus:
        """Comprehensive health check with caching.

        :param use_cache: Use cached result if available
        :param force_refresh: Force refresh even if cache is valid
        :return: Health status
        """
        current_time = asyncio.get_event_loop().time()

        # Check cache validity
        if (
            use_cache
            and not force_refresh
            and self._cached_result is not None
            and current_time - self._last_check_time < self._cache_ttl
        ):
            return self._cached_result

        # Perform checks
        status_data: dict[str, Any] = {
            "healthy": True,
            "timestamp": current_time,
            "checks": {},
            "metrics": {},
        }

        await self._check_connectivity(status_data)
        await self._check_circuit_breaker(status_data)
        await self._check_performance(status_data)
        await self._run_custom_checks(status_data)

        # Create immutable status
        status = HealthStatus(**status_data)

        # Update cache
        self._cached_result = status
        self._last_check_time = current_time

        return status

    async def _check_connectivity(self, status_data: dict[str, Any]) -> None:
        """Check basic connectivity.

        :param status_data: Status data dictionary to update
        """
        try:
            start = asyncio.get_event_loop().time()
            await self._client.get_server_info()
            duration = asyncio.get_event_loop().time() - start

            # Determine status based on response time
            check_status = self._helper.determine_status_by_time(duration)

            status_data["checks"]["connectivity"] = {
                "status": check_status,
                "message": f"API accessible ({duration:.2f}s)",
                "response_time": duration,
            }
            status_data["metrics"]["connectivity_time"] = duration

        except Exception as e:
            status_data["healthy"] = False
            status_data["checks"]["connectivity"] = {
                "status": "unhealthy",
                "message": f"API unreachable: {e}",
            }

    async def _check_circuit_breaker(self, status_data: dict[str, Any]) -> None:
        """Check circuit breaker status.

        :param status_data: Status data dictionary to update
        """
        metrics = self._client.get_circuit_metrics()

        if metrics is None:
            status_data["checks"]["circuit_breaker"] = {
                "status": "disabled",
                "message": "Circuit breaker not enabled",
            }
            return

        cb_state = metrics["state"]
        success_rate = metrics["success_rate"]

        # Determine circuit breaker health
        cb_status = self._helper.determine_circuit_status(cb_state, success_rate)

        if cb_status == "unhealthy":
            status_data["healthy"] = False

        status_data["checks"]["circuit_breaker"] = {
            "status": cb_status,
            "state": cb_state,
            "success_rate": success_rate,
            "message": f"Circuit {cb_state.lower()}, {success_rate:.1%} success",
        }

        status_data["metrics"]["circuit_success_rate"] = success_rate

    async def _check_performance(self, status_data: dict[str, Any]) -> None:
        """Check performance metrics.

        :param status_data: Status data dictionary to update
        """
        success_rate = self._metrics.success_rate
        avg_time = self._metrics.avg_response_time

        # Determine performance health
        perf_status = self._helper.determine_performance_status(success_rate, avg_time)

        if perf_status == "unhealthy":
            status_data["healthy"] = False

        status_data["checks"]["performance"] = {
            "status": perf_status,
            "success_rate": success_rate,
            "failure_rate": self._metrics.failure_rate,
            "total_requests": self._metrics.total_requests,
            "avg_response_time": avg_time,
            "uptime": self._metrics.uptime,
            "message": f"{success_rate:.1%} success, {avg_time:.2f}s avg",
        }

        status_data["metrics"]["success_rate"] = success_rate
        status_data["metrics"]["avg_response_time"] = avg_time

    async def _run_custom_checks(self, status_data: dict[str, Any]) -> None:
        """Run registered custom checks.

        :param status_data: Status data dictionary to update
        """
        for name, check_func in self._custom_checks.items():
            try:
                result = await check_func(self._client)
                status_data["checks"][name] = result

                if result.get("status") == "unhealthy":
                    status_data["healthy"] = False

            except Exception as e:
                _log_if_enabled(logging.ERROR, f"Custom check '{name}' failed: {e}")
                status_data["checks"][name] = {
                    "status": "error",
                    "message": f"Check failed: {e}",
                }

    def add_custom_check(
        self,
        name: str,
        check_func: Callable[[AsyncOutlineClient], Coroutine[Any, Any, dict[str, Any]]],
    ) -> None:
        """Register custom health check function.

        :param name: Check name
        :param check_func: Async function that returns check result
        :raises ValueError: If name is empty or function is not callable
        """
        if not name or not name.strip():
            raise ValueError("Check name cannot be empty")

        if not callable(check_func):
            raise ValueError("Check function must be callable")

        self._custom_checks[name] = check_func

        _log_if_enabled(logging.DEBUG, f"Registered custom check: {name}")

    def remove_custom_check(self, name: str) -> bool:
        """Remove custom health check.

        :param name: Check name to remove
        :return: True if check was removed, False if not found
        """
        result = self._custom_checks.pop(name, None) is not None

        if result:
            _log_if_enabled(logging.DEBUG, f"Removed custom check: {name}")

        return result

    def clear_custom_checks(self) -> int:
        """Clear all custom checks.

        :return: Number of checks cleared
        """
        count = len(self._custom_checks)
        self._custom_checks.clear()

        _log_if_enabled(logging.DEBUG, f"Cleared {count} custom check(s)")

        return count

    def record_request(self, success: bool, duration: float) -> None:
        """Record request result for performance metrics.

        Uses exponential moving average (EMA) for response time smoothing.

        :param success: Whether request was successful
        :param duration: Request duration in seconds
        :raises ValueError: If duration is negative
        """
        if duration < 0:
            raise ValueError("Duration cannot be negative")

        self._metrics.total_requests += 1

        if success:
            self._metrics.successful_requests += 1
        else:
            self._metrics.failed_requests += 1

        # Exponential moving average (EMA) for smoothing
        if self._metrics.avg_response_time == 0:
            self._metrics.avg_response_time = duration
        else:
            self._metrics.avg_response_time = (
                _ALPHA * duration + (1 - _ALPHA) * self._metrics.avg_response_time
            )

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics.

        :return: Metrics dictionary
        """
        return {
            "total_requests": self._metrics.total_requests,
            "successful_requests": self._metrics.successful_requests,
            "failed_requests": self._metrics.failed_requests,
            "success_rate": self._metrics.success_rate,
            "failure_rate": self._metrics.failure_rate,
            "avg_response_time": self._metrics.avg_response_time,
            "uptime": self._metrics.uptime,
        }

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self._metrics = PerformanceMetrics()

        _log_if_enabled(logging.DEBUG, "Reset performance metrics")

    def invalidate_cache(self) -> None:
        """Manually invalidate health check cache."""
        self._cached_result = None
        self._last_check_time = 0.0

    async def wait_for_healthy(
        self,
        timeout: float = 60.0,
        check_interval: float = 5.0,
    ) -> bool:
        """Wait for service to become healthy.

        :param timeout: Maximum time to wait in seconds
        :param check_interval: Time between checks in seconds
        :return: True if service became healthy within timeout
        :raises ValueError: If timeout or check_interval is invalid
        """
        if timeout <= 0:
            raise ValueError("Timeout must be positive")

        if check_interval <= 0:
            raise ValueError("Check interval must be positive")

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                if await self.quick_check():
                    return True
            except Exception as e:
                _log_if_enabled(logging.DEBUG, f"Health check failed: {e}")

            await asyncio.sleep(check_interval)

        return False

    @property
    def custom_checks_count(self) -> int:
        """Get number of registered custom checks.

        :return: Custom check count
        """
        return len(self._custom_checks)

    @property
    def cache_valid(self) -> bool:
        """Check if cached result is still valid.

        :return: True if cache is valid
        """
        if self._cached_result is None:
            return False

        current_time = asyncio.get_event_loop().time()
        return current_time - self._last_check_time < self._cache_ttl


__all__ = [
    "HealthMonitor",
    "HealthStatus",
    "PerformanceMetrics",
]
