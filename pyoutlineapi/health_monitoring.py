"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, TYPE_CHECKING, AsyncGenerator, Protocol

from .circuit_breaker import CircuitState, CallResult
from .exceptions import APIError

if TYPE_CHECKING:
    from .base_client import BaseHTTPClient
    from .circuit_breaker import AsyncCircuitBreaker

logger = logging.getLogger(__name__)


class RequestCapable(Protocol):
    """Protocol for objects that can make HTTP requests."""

    async def request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Make an HTTP request."""
        ...


class CircuitBreakerCapable(Protocol):
    """Protocol for objects that have circuit breaker functionality."""

    _circuit_breaker: AsyncCircuitBreaker | None
    _circuit_breaker_enabled: bool
    _performance_metrics: PerformanceMetrics
    _health_checker: OutlineHealthChecker | None
    _enable_metrics_collection: bool

    async def get_circuit_breaker_status(self) -> dict[str, Any]:
        """Get circuit breaker status."""
        ...


class PerformanceMetrics:
    """Performance metrics collection and calculation."""

    def __init__(self) -> None:
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.circuit_breaker_trips = 0
        self.avg_response_time = 0.0
        self.start_time = time.time()

    def record_request(self, success: bool, duration: float) -> None:
        """Record a request result."""
        self.total_requests += 1

        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        # Update average response time (exponential moving average)
        alpha = 0.1
        if self.avg_response_time == 0:
            self.avg_response_time = duration
        else:
            self.avg_response_time = (
                alpha * duration + (1 - alpha) * self.avg_response_time
            )

    def record_circuit_trip(self) -> None:
        """Record a circuit breaker trip."""
        self.circuit_breaker_trips += 1

    @property
    def uptime(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self.start_time

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        return 1.0 - self.success_rate

    @property
    def requests_per_minute(self) -> float:
        """Calculate requests per minute."""
        uptime_minutes = self.uptime / 60
        return self.total_requests / uptime_minutes if uptime_minutes > 0 else 0.0

    @property
    def health_status(self) -> str:
        """Get overall health status."""
        if self.success_rate > 0.9:
            return "healthy"
        elif self.success_rate > 0.5:
            return "degraded"
        else:
            return "unhealthy"

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "circuit_breaker_trips": self.circuit_breaker_trips,
            "avg_response_time": self.avg_response_time,
            "uptime": self.uptime,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "requests_per_minute": self.requests_per_minute,
            "health_status": self.health_status,
        }


class OutlineHealthChecker:
    """Health checker implementation for Outline API."""

    def __init__(self, client: BaseHTTPClient | RequestCapable) -> None:
        self.client = client
        self._last_check_time = 0.0
        self._cached_result = True
        self._cache_ttl = 30.0  # Cache health check for 30 seconds

    async def check_health(self) -> bool:
        """
        Check if the Outline server is healthy.
        Uses lightweight health check with caching.
        """
        current_time = time.time()

        # Use cached result if recent
        if current_time - self._last_check_time < self._cache_ttl:
            return self._cached_result

        try:
            # Lightweight health check - just get server info
            response_data = await self.client.request("GET", "server")
            self._cached_result = bool(response_data)
            self._last_check_time = current_time
            return self._cached_result

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            self._cached_result = False
            self._last_check_time = current_time
            return False


class HealthMonitoringMixin(RequestCapable):
    """Mixin for health monitoring capabilities."""

    # Declare attributes that should be present in implementing classes
    _circuit_breaker: AsyncCircuitBreaker | None
    _circuit_breaker_enabled: bool
    _performance_metrics: PerformanceMetrics
    _health_checker: OutlineHealthChecker | None
    _enable_metrics_collection: bool

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Initialize subclass with performance metrics."""
        super().__init_subclass__(**kwargs)
        cls._setup_performance_metrics = True

    def _initialize_health_monitoring(
        self,
        enable_health_monitoring: bool = True,
        enable_metrics_collection: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize health monitoring components."""
        self._performance_metrics = PerformanceMetrics()
        self._health_checker: OutlineHealthChecker | None = None
        self._enable_metrics_collection = enable_metrics_collection

        # Setup health checker if circuit breaker is enabled
        if enable_health_monitoring and getattr(
            self, "_circuit_breaker_enabled", False
        ):
            # Type assertion: self should implement RequestCapable protocol
            self._health_checker = OutlineHealthChecker(self)  # type: ignore[arg-type]

            # Setup circuit breaker with health checker
            circuit_breaker = getattr(self, "_circuit_breaker", None)
            if circuit_breaker:
                circuit_breaker._health_checker = self._health_checker  # type: ignore[attr-defined]

            # Setup monitoring callbacks
            if self._enable_metrics_collection:
                self._setup_monitoring_callbacks()

    def _setup_monitoring_callbacks(self) -> None:
        """Setup monitoring callbacks for circuit breaker."""
        # Use getattr with default to safely access circuit breaker
        circuit_breaker = getattr(self, "_circuit_breaker", None)
        if not circuit_breaker:
            return

        # Ensure performance metrics exist
        if not hasattr(self, "_performance_metrics"):
            self._performance_metrics = PerformanceMetrics()

        def on_state_change(old_state: CircuitState, new_state: CircuitState) -> None:
            logger.warning(
                f"Circuit breaker state changed: {old_state.name} -> {new_state.name}"
            )

            if new_state == CircuitState.OPEN:
                self._performance_metrics.record_circuit_trip()

        def on_call_result(result: CallResult) -> None:
            self._performance_metrics.record_request(result.success, result.duration)

            if not result.success:
                logger.debug(f"API call failed: {result.error}")

        circuit_breaker.add_state_change_callback(on_state_change)
        circuit_breaker.add_call_callback(on_call_result)

    async def health_check(
        self, include_detailed_metrics: bool = False
    ) -> dict[str, Any]:
        """
        Enhanced health check with circuit breaker awareness.

        Args:
            include_detailed_metrics: Include detailed performance metrics

        Returns:
            Comprehensive health status
        """
        health_status: dict[str, Any] = {
            "healthy": True,
            "timestamp": time.time(),
            "checks": {},
        }

        # Basic connectivity check
        try:
            # Try to get server info to test connectivity
            # Type check: ensure self has request method
            if not hasattr(self, "request"):
                raise AttributeError("Object must implement request method")

            response_data = await self.request("GET", "server")  # type: ignore[attr-defined]
            if not response_data:
                raise APIError("Empty response from server", 500)

            health_status["checks"]["connectivity"] = {
                "status": "healthy",
                "message": "API endpoint accessible",
            }
        except Exception as e:
            health_status["healthy"] = False
            health_status["checks"]["connectivity"] = {
                "status": "unhealthy",
                "message": f"API endpoint not accessible: {e}",
            }

        # Circuit breaker health
        circuit_breaker = getattr(self, "_circuit_breaker", None)
        if circuit_breaker:
            cb_state = circuit_breaker.state
            cb_metrics = circuit_breaker.metrics

            cb_healthy = cb_state != CircuitState.OPEN and cb_metrics.failure_rate < 0.5

            health_status["checks"]["circuit_breaker"] = {
                "status": "healthy" if cb_healthy else "unhealthy",
                "state": cb_state.name,
                "failure_rate": cb_metrics.failure_rate,
                "message": f"Circuit breaker is {cb_state.name.lower()}",
            }

            if not cb_healthy:
                health_status["healthy"] = False

        # Performance metrics check
        perf_metrics = self.get_performance_metrics()
        success_rate = perf_metrics["success_rate"]

        perf_healthy = success_rate > 0.8
        health_status["checks"]["performance"] = {
            "status": "healthy"
            if perf_healthy
            else "degraded"
            if success_rate > 0.5
            else "unhealthy",
            "success_rate": success_rate,
            "avg_response_time": perf_metrics["avg_response_time"],
            "message": f"Success rate: {success_rate:.1%}",
        }

        if not perf_healthy:
            health_status["healthy"] = health_status["healthy"] and success_rate > 0.5

        # Add detailed metrics if requested
        if include_detailed_metrics:
            health_status["detailed_metrics"] = perf_metrics
            circuit_breaker = getattr(self, "_circuit_breaker", None)
            if circuit_breaker and hasattr(self, "get_circuit_breaker_status"):
                health_status[
                    "circuit_breaker_status"
                ] = await self.get_circuit_breaker_status()  # type: ignore[attr-defined]

        return health_status

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics."""
        if not hasattr(self, "_performance_metrics"):
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "circuit_breaker_trips": 0,
                "avg_response_time": 0.0,
                "uptime": 0.0,
                "success_rate": 1.0,
                "failure_rate": 0.0,
                "requests_per_minute": 0.0,
                "health_status": "healthy",
            }

        metrics = self._performance_metrics.to_dict()

        # Add circuit breaker metrics if available
        circuit_breaker = getattr(self, "_circuit_breaker", None)
        if circuit_breaker:
            cb_metrics = circuit_breaker.metrics
            metrics["circuit_breaker"] = {
                "state": circuit_breaker.state.name,
                "failure_rate": cb_metrics.failure_rate,
                "trips": self._performance_metrics.circuit_breaker_trips,
            }

        return metrics

    @asynccontextmanager
    async def circuit_protected_operation(self) -> AsyncGenerator[None, None]:
        """
        Context manager for protecting custom operations with circuit breaker.

        Usage:
            async with client.circuit_protected_operation():
                # Your custom API operations here
                result = await some_custom_operation()
        """
        circuit_breaker = getattr(self, "_circuit_breaker", None)
        if not circuit_breaker:
            yield
            return

        async with circuit_breaker.protect_context():
            yield

    @property
    def is_healthy(self) -> bool:
        """Check if the last health check passed."""
        if not hasattr(self, "_performance_metrics"):
            return True
        return self._performance_metrics.health_status != "unhealthy"
