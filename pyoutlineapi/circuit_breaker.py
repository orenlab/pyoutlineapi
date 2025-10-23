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
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from .exceptions import CircuitOpenError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def _log_if_enabled(level: int, message: str, **kwargs: object) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    :param kwargs: Additional logging kwargs
    """
    if logger.isEnabledFor(level):
        logger.log(level, message, **kwargs)


class CircuitState(Enum):
    """Circuit breaker states.

    CLOSED: Normal operation, requests pass through
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
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    call_timeout: float = 10.0

    def __post_init__(self) -> None:
        """Validate configuration.

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
    """Circuit breaker metrics with thread-safe operations."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    state_changes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate.

        :return: Success rate as decimal (0.0 to 1.0)
        """
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate.

        :return: Failure rate as decimal (0.0 to 1.0)
        """
        return 1.0 - self.success_rate

    def to_dict(self) -> dict[str, int | float]:
        """Convert metrics to dictionary for serialization.

        :return: Dictionary representation
        """
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "state_changes": self.state_changes,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
        }


class CircuitBreaker:
    """Enhanced circuit breaker with proper timeout handling and thread-safety.

    Implements the circuit breaker pattern to prevent cascading failures
    in distributed systems. Uses monotonic clock for accurate timing.

    Thread-safe: All state changes are protected by asyncio.Lock.
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
        """Get current state.

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
        await self._check_state()

        if self._state == CircuitState.OPEN:
            # Calculate time until recovery
            time_since_failure = (
                asyncio.get_event_loop().time() - self._last_failure_time
            )
            retry_after = max(0.0, self._config.recovery_timeout - time_since_failure)

            raise CircuitOpenError(
                f"Circuit '{self._name}' is open",
                retry_after=retry_after,
            )

        start_time = asyncio.get_event_loop().time()

        try:
            # Use wait_for for timeout enforcement
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self._config.call_timeout,
            )

            duration = asyncio.get_event_loop().time() - start_time
            await self._record_success(duration)

            return result

        except asyncio.TimeoutError as e:
            duration = asyncio.get_event_loop().time() - start_time

            _log_if_enabled(
                logging.WARNING,
                f"Circuit '{self._name}': timeout after {duration:.2f}s "
                f"(limit: {self._config.call_timeout}s)",
            )

            await self._record_failure(duration, e)

            from .exceptions import TimeoutError as OutlineTimeoutError

            raise OutlineTimeoutError(
                f"Circuit '{self._name}': timeout after {self._config.call_timeout}s",
                timeout=self._config.call_timeout,
                operation=self._name,
            ) from e

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            await self._record_failure(duration, e)
            raise

    async def _check_state(self) -> None:
        """Check and transition state if needed.

        Uses pattern matching for clear state transitions.
        """
        async with self._lock:
            current_time = asyncio.get_event_loop().time()

            match self._state:
                case CircuitState.OPEN:
                    # Check if recovery timeout has elapsed
                    time_since_failure = current_time - self._last_failure_time
                    if time_since_failure >= self._config.recovery_timeout:
                        _log_if_enabled(
                            logging.INFO,
                            f"Circuit '{self._name}': attempting recovery "
                            f"after {time_since_failure:.1f}s",
                        )
                        await self._transition_to(CircuitState.HALF_OPEN)

                case CircuitState.CLOSED:
                    # Check if failure threshold exceeded
                    if self._failure_count >= self._config.failure_threshold:
                        _log_if_enabled(
                            logging.WARNING,
                            f"Circuit '{self._name}': opening due to "
                            f"{self._failure_count} failures "
                            f"(threshold: {self._config.failure_threshold})",
                        )
                        await self._transition_to(CircuitState.OPEN)

                case CircuitState.HALF_OPEN:
                    # Half-open state is stable, no automatic transitions
                    pass

    async def _record_success(self, duration: float) -> None:
        """Record successful call with metrics update.

        :param duration: Call duration in seconds
        """
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.successful_calls += 1
            self._metrics.last_success_time = asyncio.get_event_loop().time()

            if self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                if self._failure_count > 0:
                    _log_if_enabled(
                        logging.DEBUG,
                        f"Circuit '{self._name}': resetting "
                        f"{self._failure_count} failures after success",
                    )
                    self._failure_count = 0

            elif self._state == CircuitState.HALF_OPEN:
                # Count successes in half-open state
                self._success_count += 1

                if self._success_count >= self._config.success_threshold:
                    _log_if_enabled(
                        logging.INFO,
                        f"Circuit '{self._name}': closing after "
                        f"{self._success_count} consecutive successes "
                        f"(threshold: {self._config.success_threshold})",
                    )
                    await self._transition_to(CircuitState.CLOSED)

    async def _record_failure(self, duration: float, error: Exception) -> None:
        """Record failed call with metrics update.

        :param duration: Call duration in seconds
        :param error: Exception that occurred
        """
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.failed_calls += 1

            self._failure_count += 1
            self._last_failure_time = asyncio.get_event_loop().time()
            self._metrics.last_failure_time = self._last_failure_time

            error_type = type(error).__name__

            _log_if_enabled(
                logging.DEBUG,
                f"Circuit '{self._name}': failure #{self._failure_count} "
                f"({error_type}) after {duration:.2f}s",
            )

            # In half-open state, any failure reopens the circuit
            if self._state == CircuitState.HALF_OPEN:
                _log_if_enabled(
                    logging.WARNING,
                    f"Circuit '{self._name}': recovery failed, reopening",
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
        self._last_state_change = asyncio.get_event_loop().time()

        _log_if_enabled(
            logging.INFO,
            f"Circuit '{self._name}': {old_state.name} -> {new_state.name}",
        )

        # State-specific cleanup
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

        Clears all counters and metrics. Use with caution.
        """
        async with self._lock:
            _log_if_enabled(logging.INFO, f"Circuit '{self._name}': manual reset")

            await self._transition_to(CircuitState.CLOSED)
            self._metrics = CircuitMetrics()
            self._failure_count = 0
            self._success_count = 0

    def is_open(self) -> bool:
        """Check if circuit is open.

        :return: True if circuit is open
        """
        return self._state == CircuitState.OPEN

    def is_half_open(self) -> bool:
        """Check if circuit is half-open.

        :return: True if circuit is half-open
        """
        return self._state == CircuitState.HALF_OPEN

    def is_closed(self) -> bool:
        """Check if circuit is closed.

        :return: True if circuit is closed
        """
        return self._state == CircuitState.CLOSED

    def get_time_since_last_state_change(self) -> float:
        """Get time elapsed since last state change.

        :return: Time in seconds
        """
        return asyncio.get_event_loop().time() - self._last_state_change


__all__ = [
    "CircuitBreaker",
    "CircuitConfig",
    "CircuitMetrics",
    "CircuitState",
]
