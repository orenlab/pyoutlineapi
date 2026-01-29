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
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from .common_types import Constants
from .exceptions import CircuitOpenError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states.

    CLOSED: Normal operation, requests pass through (hot path)
    OPEN: Failures exceeded threshold, requests blocked
    HALF_OPEN: Testing recovery, limited requests allowed
    """

    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass(frozen=True, slots=True)
class CircuitConfig:
    """Circuit breaker configuration with validation.

    Immutable configuration to prevent runtime modification.
    Uses slots for memory efficiency (~40 bytes per instance).
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    call_timeout: float = 10.0

    def __post_init__(self) -> None:
        """Validate configuration at creation time.

        :raises ValueError: If any configuration value is invalid
        """
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_timeout < 1.0:
            raise ValueError("recovery_timeout must be >= 1.0")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if self.call_timeout < 0.1:
            raise ValueError("call_timeout must be >= 0.1")


@dataclass(slots=True)
class CircuitMetrics:
    """Circuit breaker metrics with efficient storage.

    Uses slots for memory efficiency (~80 bytes per instance).
    All calculations are O(1) with no allocations.
    """

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    state_changes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate (O(1), no allocations).

        :return: Success rate as decimal (0.0 to 1.0)
        """
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate (O(1), no allocations).

        :return: Failure rate as decimal (0.0 to 1.0)
        """
        return 1.0 - self.success_rate

    def to_dict(self) -> dict[str, int | float]:
        """Convert metrics to dictionary for serialization.

        Pre-computes rates to avoid repeated calculations.

        :return: Dictionary representation
        """
        success_rate = self.success_rate  # Calculate once
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "state_changes": self.state_changes,
            "success_rate": success_rate,
            "failure_rate": 1.0 - success_rate,  # Reuse calculation
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
        }


class CircuitBreaker:
    """High-performance circuit breaker with lock-free fast path.

    Implements the circuit breaker pattern to prevent cascading failures
    in distributed systems with minimal overhead for the common case.
    """

    __slots__ = (
        "_config",
        "_failure_count",
        "_last_failure_time",
        "_last_state_change",
        "_lock",
        "_metrics",
        "_name",
        "_state",
        "_success_count",
    )

    def __init__(self, name: str, config: CircuitConfig | None = None) -> None:
        """Initialize circuit breaker.

        :param name: Circuit breaker name (for logging and identification)
        :param config: Circuit breaker configuration
        :raises ValueError: If name is empty
        """
        if not name or not name.strip():
            raise ValueError("Circuit breaker name cannot be empty")

        self._name = name.strip()
        self._config = config or CircuitConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._last_state_change = 0.0

        self._metrics = CircuitMetrics()
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        """Get circuit breaker name.

        :return: Circuit name
        """
        return self._name

    @property
    def config(self) -> CircuitConfig:
        """Get configuration.

        :return: Circuit configuration (immutable)
        """
        return self._config

    @property
    def state(self) -> CircuitState:
        """Get current state (lock-free read).

        :return: Current circuit state
        """
        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        """Get metrics snapshot.

        :return: Circuit metrics object
        """
        return self._metrics

    def get_metrics_snapshot(self) -> dict[str, int | float]:
        """Get thread-safe metrics snapshot.

        :return: Dictionary with current metrics
        """
        return self._metrics.to_dict()

    async def call(
        self,
        func: Callable[P, Awaitable[T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Execute function with circuit breaker protection.

        :param func: Async function to execute
        :param args: Positional arguments
        :param kwargs: Keyword arguments
        :return: Function result
        :raises CircuitOpenError: If circuit is open
        :raises TimeoutError: If call exceeds timeout
        """
        current_state = self._state  # Atomic read

        if (
            current_state == CircuitState.CLOSED
            and self._failure_count < self._config.failure_threshold
        ):
            # Fast path: no state checking needed for closed circuit
            return await self._execute_call(func, args, kwargs)

        # Slow path: need state checking/transition
        await self._check_state()

        if self._state == CircuitState.OPEN:
            # Calculate time until recovery
            current_time = time.monotonic()
            time_since_failure = current_time - self._last_failure_time
            retry_after = max(0.0, self._config.recovery_timeout - time_since_failure)

            raise CircuitOpenError(
                f"Circuit '{self._name}' is open",
                retry_after=retry_after,
            )

        return await self._execute_call(func, args, kwargs)

    async def _execute_call(
        self,
        func: Callable[P, Awaitable[T]],
        args: tuple,
        kwargs: dict,
    ) -> T:
        """Execute the actual function call with timeout and metrics.

        Extracted to separate method for code reuse between fast and slow paths.

        :param func: Function to execute
        :param args: Positional arguments
        :param kwargs: Keyword arguments
        :return: Function result
        :raises TimeoutError: If call exceeds timeout
        """
        start_time = time.monotonic()

        try:
            # Use wait_for for timeout enforcement
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self._config.call_timeout,
            )

            duration = time.monotonic() - start_time
            await self._record_success(duration)

            return result

        except asyncio.TimeoutError as e:
            duration = time.monotonic() - start_time

            if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                logger.warning(
                    "Circuit '%s': timeout after %.2fs (limit: %.2fs)",
                    self._name,
                    duration,
                    self._config.call_timeout,
                )

            await self._record_failure(duration, e)

            from .exceptions import OutlineTimeoutError as OutlineTimeoutError

            raise OutlineTimeoutError(
                f"Circuit '{self._name}': timeout after {self._config.call_timeout}s",
                timeout=self._config.call_timeout,
                operation=self._name,
            ) from e

        except Exception as e:
            duration = time.monotonic() - start_time
            await self._record_failure(duration, e)
            raise

    async def _check_state(self) -> None:
        """Check and transition state if needed.

        Uses pattern matching for clear state transitions.
        Only called on slow path (not in CLOSED state fast path).
        """
        async with self._lock:
            # Cache time calculation
            current_time = time.monotonic()

            match self._state:
                case CircuitState.OPEN:
                    # Check if recovery timeout has elapsed
                    time_since_failure = current_time - self._last_failure_time
                    if time_since_failure >= self._config.recovery_timeout:
                        if logger.isEnabledFor(Constants.LOG_LEVEL_INFO):
                            logger.info(
                                "Circuit '%s': attempting recovery after %.1fs",
                                self._name,
                                time_since_failure,
                            )
                        await self._transition_to(CircuitState.HALF_OPEN)

                case CircuitState.CLOSED:
                    # Check if failure threshold exceeded
                    if self._failure_count >= self._config.failure_threshold:
                        if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                            logger.warning(
                                "Circuit '%s': opening due to %d failures (threshold: %d)",
                                self._name,
                                self._failure_count,
                                self._config.failure_threshold,
                            )
                        await self._transition_to(CircuitState.OPEN)

                case CircuitState.HALF_OPEN:
                    # Half-open state is stable, no automatic transitions
                    pass

    async def _record_success(self, duration: float) -> None:
        """Record successful call with metrics update.

        :param duration: Call duration in seconds
        """
        # Always update metrics (atomic operations on integers are safe)
        self._metrics.total_calls += 1
        self._metrics.successful_calls += 1
        self._metrics.last_success_time = time.monotonic()

        # Fast path: CLOSED state with no failures
        if self._state == CircuitState.CLOSED and self._failure_count == 0:
            return  # No lock needed, no state change

        # Slow path: need state transition logic
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                if self._failure_count > 0:
                    if logger.isEnabledFor(Constants.LOG_LEVEL_DEBUG):
                        logger.debug(
                            "Circuit '%s': resetting %d failures after success",
                            self._name,
                            self._failure_count,
                        )
                    self._failure_count = 0

            elif self._state == CircuitState.HALF_OPEN:
                # Count successes in half-open state
                self._success_count += 1

                if self._success_count >= self._config.success_threshold:
                    if logger.isEnabledFor(Constants.LOG_LEVEL_INFO):
                        logger.info(
                            "Circuit '%s': closing after %d consecutive successes (threshold: %d)",
                            self._name,
                            self._success_count,
                            self._config.success_threshold,
                        )
                    await self._transition_to(CircuitState.CLOSED)

    async def _record_failure(self, duration: float, error: Exception) -> None:
        """Record failed call with metrics update.

        :param duration: Call duration in seconds
        :param error: Exception that occurred
        """
        async with self._lock:
            # Update metrics
            self._metrics.total_calls += 1
            self._metrics.failed_calls += 1

            self._failure_count += 1

            # Cache time calculation
            current_time = time.monotonic()
            self._last_failure_time = current_time
            self._metrics.last_failure_time = current_time

            # Log failure
            if logger.isEnabledFor(Constants.LOG_LEVEL_DEBUG):
                error_type = type(error).__name__
                logger.debug(
                    "Circuit '%s': failure #%d (%s) after %.2fs",
                    self._name,
                    self._failure_count,
                    error_type,
                    duration,
                )

            # In half-open state, any failure reopens the circuit
            if self._state == CircuitState.HALF_OPEN:
                if logger.isEnabledFor(Constants.LOG_LEVEL_WARNING):
                    logger.warning(
                        "Circuit '%s': recovery failed, reopening", self._name
                    )
                await self._transition_to(CircuitState.OPEN)

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to new state with cleanup.

        :param new_state: Target state
        """
        if self._state == new_state:
            return

        old_state = self._state
        self._state = new_state
        self._metrics.state_changes += 1
        self._last_state_change = time.monotonic()

        if logger.isEnabledFor(Constants.LOG_LEVEL_INFO):
            logger.info(
                "Circuit '%s': %s -> %s",
                self._name,
                old_state.name,
                new_state.name,
            )

        # State-specific cleanup using pattern matching
        match new_state:
            case CircuitState.CLOSED:
                self._failure_count = 0
                self._success_count = 0

            case CircuitState.HALF_OPEN:
                self._success_count = 0
                self._failure_count = 0

            case CircuitState.OPEN:
                self._success_count = 0
                # Keep failure_count for metrics

    async def reset(self) -> None:
        """Manually reset circuit breaker to closed state.

        Clears all counters and metrics. Use with caution in production.
        """
        async with self._lock:
            if logger.isEnabledFor(Constants.LOG_LEVEL_INFO):
                logger.info("Circuit '%s': manual reset", self._name)

            await self._transition_to(CircuitState.CLOSED)
            self._metrics = CircuitMetrics()
            self._failure_count = 0
            self._success_count = 0

    def is_open(self) -> bool:
        """Check if circuit is open (lock-free read).

        :return: True if circuit is open
        """
        return self._state == CircuitState.OPEN

    def is_half_open(self) -> bool:
        """Check if circuit is half-open (lock-free read).

        :return: True if circuit is half-open
        """
        return self._state == CircuitState.HALF_OPEN

    def is_closed(self) -> bool:
        """Check if circuit is closed (lock-free read).

        :return: True if circuit is closed
        """
        return self._state == CircuitState.CLOSED

    def get_time_since_last_state_change(self) -> float:
        """Get time elapsed since last state change.

        :return: Time in seconds
        """
        return time.monotonic() - self._last_state_change


__all__ = [
    "CircuitBreaker",
    "CircuitConfig",
    "CircuitMetrics",
    "CircuitState",
]
