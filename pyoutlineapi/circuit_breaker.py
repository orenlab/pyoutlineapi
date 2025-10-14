"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Simplified circuit breaker pattern (optional).

The circuit breaker prevents cascading failures by temporarily blocking
requests when the service is experiencing issues.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Awaitable, Callable, ParamSpec, TypeVar

from .exceptions import CircuitOpenError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
    """
    Circuit breaker states.

    States:
        CLOSED: Normal operation, requests pass through
        OPEN: Circuit is broken, blocking all requests
        HALF_OPEN: Testing if service has recovered
    """

    CLOSED = auto()  # Normal operation
    OPEN = auto()  # Failing, blocking calls
    HALF_OPEN = auto()  # Testing recovery


@dataclass(frozen=True)
class CircuitConfig:
    """
    Circuit breaker configuration.

    Simplified configuration with sane defaults for most use cases.

    Attributes:
        failure_threshold: Number of failures before opening circuit (default: 5)
        recovery_timeout: Seconds to wait before attempting recovery (default: 60.0)
        success_threshold: Successes needed to close circuit from half-open (default: 2)
        call_timeout: Maximum seconds for a single call (default: 30.0)

    Example:
        >>> from pyoutlineapi.circuit_breaker import CircuitConfig
        >>> config = CircuitConfig(
        ...     failure_threshold=10,
        ...     recovery_timeout=120.0,
        ... )
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    call_timeout: float = 30.0


@dataclass
class CircuitMetrics:
    """
    Circuit breaker metrics.

    Tracks operational statistics for monitoring and debugging.
    """

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    state_changes: int = 0

    @property
    def success_rate(self) -> float:
        """
        Calculate success rate.

        Returns:
            float: Success rate (0.0 to 1.0)

        Example:
            >>> metrics = circuit_breaker.metrics
            >>> print(f"Success rate: {metrics.success_rate:.2%}")
        """
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def failure_rate(self) -> float:
        """
        Calculate failure rate.

        Returns:
            float: Failure rate (0.0 to 1.0)
        """
        return 1.0 - self.success_rate


class CircuitBreaker:
    """
    Simplified circuit breaker implementation.

    Features:
    - Lightweight (no background tasks by default)
    - Minimal overhead when working properly
    - Easy to disable completely
    - Automatic recovery testing
    - Proper timeout handling

    Example:
        >>> from pyoutlineapi.circuit_breaker import CircuitBreaker, CircuitConfig
        >>>
        >>> config = CircuitConfig(failure_threshold=5)
        >>> breaker = CircuitBreaker("my-service", config)
        >>>
        >>> async def risky_operation():
        ...     # Some operation that might fail
        ...     return await some_api_call()
        >>>
        >>> try:
        ...     result = await breaker.call(risky_operation)
        ... except CircuitOpenError:
        ...     print("Circuit is open, service unavailable")
    """

    __slots__ = (
        "name",
        "config",
        "_state",
        "_failure_count",
        "_success_count",
        "_last_failure_time",
        "_metrics",
        "_lock",
    )

    def __init__(
        self,
        name: str,
        config: CircuitConfig | None = None,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            name: Circuit breaker identifier (for logging/monitoring)
            config: Circuit breaker configuration (uses defaults if None)

        Example:
            >>> breaker = CircuitBreaker("outline-api")
            >>> # Or with custom config
            >>> config = CircuitConfig(failure_threshold=10)
            >>> breaker = CircuitBreaker("outline-api", config)
        """
        self.name = name
        self.config = config or CircuitConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0

        self._metrics = CircuitMetrics()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """
        Get current circuit breaker state.

        Returns:
            CircuitState: Current state (CLOSED, OPEN, or HALF_OPEN)

        Example:
            >>> print(f"Circuit state: {breaker.state.name}")
        """
        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        """
        Get circuit breaker metrics.

        Returns:
            CircuitMetrics: Current metrics

        Example:
            >>> metrics = breaker.metrics
            >>> print(f"Total calls: {metrics.total_calls}")
            >>> print(f"Success rate: {metrics.success_rate:.2%}")
        """
        return self._metrics

    async def call(
        self,
        func: Callable[P, Awaitable[T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            T: Function result

        Raises:
            CircuitOpenError: If circuit is open
            asyncio.TimeoutError: If call exceeds timeout (caught and recorded as failure)

        Example:
            >>> async def get_data():
            ...     return await client.get_server_info()
            >>>
            >>> try:
            ...     data = await breaker.call(get_data)
            ... except CircuitOpenError as e:
            ...     print(f"Circuit open, retry after {e.retry_after}s")
        """
        # Check state
        await self._check_state()

        if self._state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open",
                retry_after=self.config.recovery_timeout,
            )

        # Execute with timeout
        start_time = time.time()

        try:
            # Use asyncio.wait_for with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.call_timeout,
            )

            # Record success
            duration = time.time() - start_time
            await self._record_success(duration)

            return result

        except asyncio.TimeoutError as e:
            # Record timeout as failure
            duration = time.time() - start_time
            logger.warning(
                f"Circuit '{self.name}': Call timed out after {duration:.2f}s"
            )
            await self._record_failure(duration, e)

            # Convert asyncio.TimeoutError to our custom TimeoutError
            # so it can be caught and retried properly
            from .exceptions import TimeoutError as OutlineTimeoutError
            raise OutlineTimeoutError(
                f"Circuit '{self.name}': Operation timed out after {self.config.call_timeout}s",
                timeout=self.config.call_timeout,
                operation=self.name,
            ) from e

        except Exception as e:
            # Record failure
            duration = time.time() - start_time
            await self._record_failure(duration, e)
            raise

    async def _check_state(self) -> None:
        """Check and transition state if needed using modern match statement."""
        async with self._lock:
            current_time = time.time()

            match self._state:
                case CircuitState.OPEN:
                    # Check if recovery timeout passed
                    if (
                        current_time - self._last_failure_time
                        >= self.config.recovery_timeout
                    ):
                        logger.info(
                            f"Circuit '{self.name}': Attempting recovery (OPEN -> HALF_OPEN)"
                        )
                        await self._transition_to(CircuitState.HALF_OPEN)

                case CircuitState.CLOSED:
                    # Check if should open
                    if self._failure_count >= self.config.failure_threshold:
                        logger.warning(
                            f"Circuit '{self.name}': Opening circuit due to {self._failure_count} failures"
                        )
                        await self._transition_to(CircuitState.OPEN)

                case CircuitState.HALF_OPEN:
                    # No action needed in half-open during check
                    pass

    async def _record_success(self, duration: float) -> None:
        """Record successful call."""
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.successful_calls += 1

            if self._state == CircuitState.CLOSED:
                # Reset failure count on success in CLOSED state
                # This prevents old failures from accumulating
                if self._failure_count > 0:
                    logger.debug(
                        f"Circuit '{self.name}': Resetting {self._failure_count} failures after success"
                    )
                    self._failure_count = 0

            elif self._state == CircuitState.HALF_OPEN:
                self._success_count += 1

                # Close circuit if threshold met
                if self._success_count >= self.config.success_threshold:
                    logger.info(
                        f"Circuit '{self.name}': Closing circuit after {self._success_count} successful calls"
                    )
                    await self._transition_to(CircuitState.CLOSED)

    async def _record_failure(self, duration: float, error: Exception) -> None:
        """Record failed call."""
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.failed_calls += 1

            self._failure_count += 1
            self._last_failure_time = time.time()

            error_type = type(error).__name__
            logger.debug(
                f"Circuit '{self.name}': Failure recorded ({error_type}) - "
                f"total failures: {self._failure_count}"
            )

            # In half-open, any failure opens circuit
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"Circuit '{self.name}': Recovery failed, reopening circuit"
                )
                await self._transition_to(CircuitState.OPEN)

    async def _transition_to(self, new_state: CircuitState) -> None:
        """
        Transition to new state with proper counter management.

        Uses match statement for clean state-based counter resets.
        """
        if self._state == new_state:
            return

        old_state = self._state.name
        self._state = new_state
        self._metrics.state_changes += 1

        logger.info(f"Circuit '{self.name}': State transition {old_state} -> {new_state.name}")

        match new_state:
            case CircuitState.CLOSED:
                self._failure_count = 0
                self._success_count = 0

            case CircuitState.HALF_OPEN:
                # Reset success count to test recovery
                self._success_count = 0
                self._failure_count = 0

            case CircuitState.OPEN:
                # Keep failure_count, reset success
                self._success_count = 0

    async def reset(self) -> None:
        """
        Manually reset circuit breaker to CLOSED state.

        Clears all counters and metrics. Useful for administrative
        recovery or testing.

        Example:
            >>> # Manually reset after fixing the underlying issue
            >>> await breaker.reset()
            >>> print(f"State: {breaker.state.name}")  # CLOSED
        """
        async with self._lock:
            logger.info(f"Circuit '{self.name}': Manual reset")
            await self._transition_to(CircuitState.CLOSED)
            self._metrics = CircuitMetrics()


__all__ = [
    "CircuitState",
    "CircuitConfig",
    "CircuitMetrics",
    "CircuitBreaker",
]