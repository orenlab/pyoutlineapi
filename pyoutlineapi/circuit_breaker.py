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

from .exceptions import CircuitOpenError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass(frozen=True, slots=True)  # Python 3.10+
class CircuitConfig:
    """Circuit breaker configuration with slots for memory efficiency.

    Attributes:
        failure_threshold: Failures before opening (default: 5)
        recovery_timeout: Seconds before recovery attempt (default: 60.0)
        success_threshold: Successes needed to close from half-open (default: 2)
        call_timeout: Max seconds for single call (default: 10.0)
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    call_timeout: float = 10.0

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_timeout < 1.0:
            raise ValueError("recovery_timeout must be >= 1.0")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if self.call_timeout < 1.0:
            raise ValueError("call_timeout must be >= 1.0")


@dataclass(slots=True)  # Python 3.10+
class CircuitMetrics:
    """Circuit breaker metrics with slots."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    state_changes: int = 0
    last_failure_time: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        return 1.0 - self.success_rate


class CircuitBreaker:
    """Enhanced circuit breaker with better timeout handling.

    IMPROVEMENTS:
    - Proper timeout conversion
    - Better error handling
    - Enhanced metrics
    """

    __slots__ = (
        "_failure_count",
        "_last_failure_time",
        "_lock",
        "_metrics",
        "_state",
        "_success_count",
        "config",
        "name",
    )

    def __init__(self, name: str, config: CircuitConfig | None = None) -> None:
        """Initialize circuit breaker."""
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
        """Get current state."""
        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        """Get metrics."""
        return self._metrics

    async def call(
        self,
        func: Callable[P, Awaitable[T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Execute function with circuit breaker protection."""
        await self._check_state()

        if self._state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open",
                retry_after=self.config.recovery_timeout,
            )

        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.call_timeout,
            )

            duration = time.time() - start_time
            await self._record_success(duration)

            return result

        except asyncio.TimeoutError as e:
            duration = time.time() - start_time
            logger.warning(f"Circuit '{self.name}': timeout after {duration:.2f}s")
            await self._record_failure(duration, e)

            # Convert to OutlineTimeoutError
            from .exceptions import TimeoutError as OutlineTimeoutError

            raise OutlineTimeoutError(
                f"Circuit '{self.name}': timeout after {self.config.call_timeout}s",
                timeout=self.config.call_timeout,
                operation=self.name,
            ) from e

        except Exception as e:
            duration = time.time() - start_time
            await self._record_failure(duration, e)
            raise

    async def _check_state(self) -> None:
        """Check and transition state if needed."""
        async with self._lock:
            current_time = time.time()

            match self._state:
                case CircuitState.OPEN:
                    if (
                        current_time - self._last_failure_time
                        >= self.config.recovery_timeout
                    ):
                        logger.info(f"Circuit '{self.name}': attempting recovery")
                        await self._transition_to(CircuitState.HALF_OPEN)

                case CircuitState.CLOSED:
                    if self._failure_count >= self.config.failure_threshold:
                        logger.warning(
                            f"Circuit '{self.name}': opening due to {self._failure_count} failures"
                        )
                        await self._transition_to(CircuitState.OPEN)

                case CircuitState.HALF_OPEN:
                    pass

    async def _record_success(self, duration: float) -> None:
        """Record successful call."""
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.successful_calls += 1

            if self._state == CircuitState.CLOSED:
                if self._failure_count > 0:
                    logger.debug(
                        f"Circuit '{self.name}': resetting {self._failure_count} failures"
                    )
                    self._failure_count = 0

            elif self._state == CircuitState.HALF_OPEN:
                self._success_count += 1

                if self._success_count >= self.config.success_threshold:
                    logger.info(
                        f"Circuit '{self.name}': closing after {self._success_count} successes"
                    )
                    await self._transition_to(CircuitState.CLOSED)

    async def _record_failure(self, duration: float, error: Exception) -> None:
        """Record failed call."""
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.failed_calls += 1

            self._failure_count += 1
            self._last_failure_time = time.time()
            self._metrics.last_failure_time = self._last_failure_time

            error_type = type(error).__name__
            logger.debug(
                f"Circuit '{self.name}': failure ({error_type}) - "
                f"total: {self._failure_count}"
            )

            if self._state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit '{self.name}': recovery failed")
                await self._transition_to(CircuitState.OPEN)

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to new state."""
        if self._state == new_state:
            return

        old_state = self._state.name
        self._state = new_state
        self._metrics.state_changes += 1

        logger.info(f"Circuit '{self.name}': {old_state} -> {new_state.name}")

        match new_state:
            case CircuitState.CLOSED:
                self._failure_count = 0
                self._success_count = 0

            case CircuitState.HALF_OPEN:
                self._success_count = 0
                self._failure_count = 0

            case CircuitState.OPEN:
                self._success_count = 0

    async def reset(self) -> None:
        """Manually reset circuit breaker."""
        async with self._lock:
            logger.info(f"Circuit '{self.name}': manual reset")
            await self._transition_to(CircuitState.CLOSED)
            self._metrics = CircuitMetrics()


__all__ = [
    "CircuitBreaker",
    "CircuitConfig",
    "CircuitMetrics",
    "CircuitState",
]
