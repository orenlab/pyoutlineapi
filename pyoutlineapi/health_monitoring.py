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
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from .client import AsyncOutlineClient

logger = logging.getLogger(__name__)

_MIN_CACHE_TTL: Final[float] = 1.0
_MAX_CACHE_TTL: Final[float] = 300.0
_ALPHA: Final[float] = 0.1  # EMA smoothing factor (10% weight to new values)

# Response time thresholds for status determination
_THRESHOLD_HEALTHY: Final[float] = 1.0
_THRESHOLD_WARNING: Final[float] = 3.0

# Success rate thresholds
_SUCCESS_RATE_EXCELLENT: Final[float] = 0.95
_SUCCESS_RATE_GOOD: Final[float] = 0.9
_SUCCESS_RATE_ACCEPTABLE: Final[float] = 0.7
_SUCCESS_RATE_DEGRADED: Final[float] = 0.5


def _log_if_enabled(level: int, message: str) -> None:
    """Centralized logging with log-level guard.

    :param level: Logging level
    :param message: Log message
    """
    if logger.isEnabledFor(level):
        logger.log(level, message)


@dataclass(slots=True, frozen=True)
class HealthStatus:
    """Immutable health check result with optimized properties."""

    healthy: bool
    timestamp: float
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def failed_checks(self) -> list[str]:
        """Get failed checks.

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
        """Get warning checks.

        :return: List of warning check names
        """
        return [
            name
            for name, result in self.checks.items()
            if result.get("status") == "warning"
        ]

    @property
    def total_checks(self) -> int:
        """Get total check count.

        :return: Total check count
        """
        return len(self.checks)

    @property
    def passed_checks(self) -> int:
        """Get passed check count.

        :return: Passed check count
        """
        return sum(
            1 for result in self.checks.values() if result.get("status") == "healthy"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with cached properties.

        :return: Dictionary representation
        """
        return {
            "healthy": self.healthy,
            "degraded": self.is_degraded,  # Cached
            "timestamp": self.timestamp,
            "checks": self.checks,
            "metrics": self.metrics,
            "failed_checks": self.failed_checks,  # Cached
            "warning_checks": self.warning_checks,  # Cached
            "total_checks": self.total_checks,  # Cached
            "passed_checks": self.passed_checks,  # Cached
        }


@dataclass(slots=True)
class PerformanceMetrics:
    """Performance tracking with optimized EMA and properties."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    start_time: float = field(default_factory=time.monotonic)

    @property
    def success_rate(self) -> float:
        """Calculate success rate with fast path.

        :return: Success rate (0.0 to 1.0)
        """
        if self.total_requests == 0:
            return 1.0  # Fast path
        return self.successful_requests / self.total_requests

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate (uses success_rate).

        :return: Failure rate (0.0 to 1.0)
        """
        return 1.0 - self.success_rate

    @property
    def uptime(self) -> float:
        """Get uptime in seconds.

        :return: Uptime in seconds
        """
        return time.monotonic() - self.start_time


class HealthCheckHelper:
    """Helper for status determination."""

    __slots__ = ()  # No instance attributes

    @staticmethod
    def determine_status_by_time(duration: float) -> str:
        """Determine status using pattern matching (Python 3.10+).

        :param duration: Response time in seconds
        :return: Status string
        """
        match duration:
            case d if d < _THRESHOLD_HEALTHY:
                return "healthy"
            case d if d < _THRESHOLD_WARNING:
                return "warning"
            case _:
                return "degraded"

    @staticmethod
    def determine_circuit_status(cb_state: str, success_rate: float) -> str:
        """Determine circuit status.

        :param cb_state: Circuit breaker state
        :param success_rate: Success rate (0.0 to 1.0)
        :return: Status string
        """
        match cb_state:
            case "OPEN":
                return "unhealthy"
            case "HALF_OPEN":
                return "warning"
            case _:
                # Closed state - check success rate
                match success_rate:
                    case r if r >= _SUCCESS_RATE_GOOD:
                        return "healthy"
                    case r if r >= _SUCCESS_RATE_DEGRADED:
                        return "warning"
                    case _:
                        return "degraded"

    @staticmethod
    def determine_performance_status(success_rate: float, avg_time: float) -> str:
        """Determine performance status.

        :param success_rate: Success rate (0.0 to 1.0)
        :param avg_time: Average response time
        :return: Status string
        """
        match (success_rate, avg_time):
            case (r, t) if r > _SUCCESS_RATE_EXCELLENT and t < 1.0:
                return "healthy"
            case (r, t) if r > _SUCCESS_RATE_GOOD and t < 2.0:
                return "warning"
            case (r, _) if r > _SUCCESS_RATE_ACCEPTABLE:
                return "degraded"
            case _:
                return "unhealthy"


class HealthMonitor:
    """Health monitoring with caching and checks."""

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
        """Initialize health monitor with validation.

        :param client: AsyncOutlineClient instance
        :param cache_ttl: Cache TTL in seconds (1.0-300.0)
        :raises ValueError: If cache_ttl is invalid
        """
        # Validate cache_ttl using pattern matching
        match cache_ttl:
            case ttl if _MIN_CACHE_TTL <= ttl <= _MAX_CACHE_TTL:
                self._cache_ttl = ttl
            case _:
                raise ValueError(
                    f"cache_ttl must be between {_MIN_CACHE_TTL} and {_MAX_CACHE_TTL}"
                )

        self._client = client
        self._metrics = PerformanceMetrics()
        self._custom_checks: dict[
            str, Callable[[AsyncOutlineClient], Coroutine[Any, Any, dict[str, Any]]]
        ] = {}
        self._helper = HealthCheckHelper()
        self._cached_result: HealthStatus | None = None
        self._last_check_time: float = 0.0

    async def check(self, *, use_cache: bool = True) -> HealthStatus:
        """Perform comprehensive health check with caching.

        :param use_cache: Whether to use cached result
        :return: Health status
        """
        # Fast path: return cached result if valid
        if use_cache and self.cache_valid:
            cached = self._cached_result
            if cached is not None:
                return cached

        # Perform full health check
        current_time = time.monotonic()
        status_data: dict[str, Any] = {
            "healthy": True,
            "timestamp": current_time,
            "checks": {},
            "metrics": {},
        }

        # Run all checks concurrently for speed
        await asyncio.gather(
            self._check_connectivity(status_data),
            self._check_circuit_breaker(status_data),
            self._check_performance(status_data),
            self._run_custom_checks(status_data),
            return_exceptions=True,  # Don't fail if one check fails
        )

        # Create immutable result
        result = HealthStatus(
            healthy=status_data["healthy"],
            timestamp=status_data["timestamp"],
            checks=status_data["checks"],
            metrics=status_data["metrics"],
        )

        # Update cache
        self._cached_result = result
        self._last_check_time = current_time

        return result

    async def quick_check(self) -> bool:
        """Quick health check (connectivity only) with caching.

        :return: True if healthy
        """
        # Fast path: use cached result if available
        if self.cache_valid:
            cached = self._cached_result
            if cached is not None:
                return cached.healthy

        try:
            start = time.monotonic()
            await self._client.get_server_info()
            duration = time.monotonic() - start

            # Determine status using helper
            status = self._helper.determine_status_by_time(duration)
            return status == "healthy"

        except Exception:
            return False

    async def _check_connectivity(self, status_data: dict[str, Any]) -> None:
        """Check basic connectivity with timing.

        :param status_data: Status data to update
        """
        try:
            start = time.monotonic()
            await self._client.get_server_info()
            duration = time.monotonic() - start

            # Determine status using helper (pattern matching)
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

        :param status_data: Status data to update
        """
        metrics = self._client.get_circuit_metrics()

        # Fast path: circuit breaker disabled
        if metrics is None:
            status_data["checks"]["circuit_breaker"] = {
                "status": "disabled",
                "message": "Circuit breaker not enabled",
            }
            return

        cb_state_raw = metrics.get("state", "unknown")
        cb_state = str(cb_state_raw)

        success_rate_raw = metrics.get("success_rate", 0.0)
        try:
            success_rate = float(success_rate_raw)
        except (TypeError, ValueError):
            success_rate = 0.0

        # Determine status using helper (pattern matching)
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

        :param status_data: Status data to update
        """
        success_rate = self._metrics.success_rate
        avg_time = self._metrics.avg_response_time

        # Determine status using helper (pattern matching)
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
        """Run custom checks with error handling.

        :param status_data: Status data to update
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
        """Register custom health check with validation.

        :param name: Check name
        :param check_func: Async check function
        :raises ValueError: If name or function is invalid
        """
        # Validate using pattern matching
        match (name.strip(), callable(check_func)):
            case ("", _):
                raise ValueError("Check name cannot be empty")
            case (_, False):
                raise ValueError("Check function must be callable")
            case (valid_name, True):
                self._custom_checks[valid_name] = check_func
                _log_if_enabled(logging.DEBUG, f"Registered custom check: {valid_name}")

    def remove_custom_check(self, name: str) -> bool:
        """Remove custom check.

        :param name: Check name
        :return: True if removed
        """
        result = self._custom_checks.pop(name, None) is not None

        if result:
            _log_if_enabled(logging.DEBUG, f"Removed custom check: {name}")

        return result

    def clear_custom_checks(self) -> int:
        """Clear all custom checks.

        :return: Number cleared
        """
        count = len(self._custom_checks)
        self._custom_checks.clear()

        _log_if_enabled(logging.DEBUG, f"Cleared {count} custom check(s)")

        return count

    def record_request(self, success: bool, duration: float) -> None:
        """Record request with optimized EMA calculation.

        :param success: Request success
        :param duration: Request duration
        :raises ValueError: If duration is negative
        """
        if duration < 0:
            raise ValueError("Duration cannot be negative")

        self._metrics.total_requests += 1

        if success:
            self._metrics.successful_requests += 1
        else:
            self._metrics.failed_requests += 1

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
        """Invalidate health check cache."""
        self._cached_result = None
        self._last_check_time = 0.0

    async def wait_for_healthy(
        self,
        timeout: float = 60.0,
        check_interval: float = 5.0,
    ) -> bool:
        """Wait for service to become healthy with validation.

        :param timeout: Maximum wait time (seconds)
        :param check_interval: Time between checks (seconds)
        :return: True if healthy within timeout
        :raises ValueError: If parameters invalid
        """
        # Validate using pattern matching
        match (timeout, check_interval):
            case (t, _) if t <= 0:
                raise ValueError("Timeout must be positive")
            case (_, i) if i <= 0:
                raise ValueError("Check interval must be positive")

        start_time = time.monotonic()
        deadline = start_time + timeout

        last_error: Exception | None = None

        while True:
            try:
                if await self.quick_check():
                    return True
            except Exception as e:
                last_error = e
                _log_if_enabled(logging.DEBUG, f"Health check failed: {e}")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(check_interval, remaining))

        if last_error is not None:
            _log_if_enabled(logging.DEBUG, f"Health check failed: {last_error}")
        else:
            _log_if_enabled(logging.DEBUG, "Health check failed: timeout")

        return False

    @property
    def custom_checks_count(self) -> int:
        """Get custom check count.

        :return: Custom check count
        """
        return len(self._custom_checks)

    @property
    def cache_valid(self) -> bool:
        """Check cache validity with fast path.

        :return: True if cache valid
        """
        # Fast path: no cached result
        if self._cached_result is None:
            return False

        # Check TTL
        current_time = time.monotonic()
        return current_time - self._last_check_time < self._cache_ttl


__all__ = [
    "HealthMonitor",
    "HealthStatus",
    "PerformanceMetrics",
]
