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

import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum, auto
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Deque,
    Generic,
    ParamSpec,
    TypeVar,
    Protocol,
    runtime_checkable,
)
from weakref import WeakSet

from .exceptions import CircuitOpenError

# Type variables
P = ParamSpec("P")
T = TypeVar("T")

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """
    Circuit breaker states following the standard Circuit Breaker pattern.

    The circuit breaker transitions between these three states based on
    the success/failure rate of protected operations:

    States:
        CLOSED: Normal operation, requests pass through to the service
        OPEN: Failing fast, requests are blocked and fail immediately
        HALF_OPEN: Testing recovery, limited requests are allowed through

    State Transitions:
        CLOSED -> OPEN: When failure threshold is exceeded
        OPEN -> HALF_OPEN: After recovery timeout period
        HALF_OPEN -> CLOSED: When success threshold is met
        HALF_OPEN -> OPEN: On any failure during testing

    Examples:
        Check circuit state:

        >>> circuit = AsyncCircuitBreaker("my-service")
        >>> if circuit.state == CircuitState.OPEN:
        ...     print("Service is currently unavailable")
        >>> elif circuit.state == CircuitState.HALF_OPEN:
        ...     print("Service is being tested for recovery")
        >>> else:
        ...     print("Service is operating normally")
    """

    CLOSED = auto()  # Normal operation
    OPEN = auto()  # Failing fast, not calling the service
    HALF_OPEN = auto()  # Testing if the service has recovered


@runtime_checkable
class HealthChecker(Protocol):
    """
    Protocol for health check implementations.

    Health checkers are used by the circuit breaker to proactively
    test service health and potentially trigger early recovery
    from the OPEN state.

    Examples:
        Implement a custom health checker:

        >>> class MyHealthChecker:
        ...     async def check_health(self) -> bool:
        ...         try:
        ...             # Perform lightweight health check
        ...             response = await some_health_endpoint()
        ...             return response.status == 200
        ...         except Exception:
        ...             return False

        Use with circuit breaker:

        >>> health_checker = MyHealthChecker()
        >>> circuit = AsyncCircuitBreaker(
        ...     "my-service",
        ...     health_checker=health_checker
        ... )
    """

    async def check_health(self) -> bool:
        """
        Check if the service is healthy.

        This method should perform a lightweight check to determine
        if the protected service is available and responding correctly.
        It's called periodically when the circuit is in OPEN state
        to test for recovery.

        Returns:
            True if the service appears healthy, False otherwise

        Note:
            This method should be fast and not throw exceptions.
            Any exceptions will be caught and treated as health check failure.
        """
        ...


@dataclass(frozen=True)
class CircuitConfig:
    """
    Immutable configuration for circuit breaker behavior.

    This configuration controls all aspects of circuit breaker operation,
    including when to open the circuit, how long to wait for recovery,
    and how to evaluate service health.

    Args:
        failure_threshold: Number of consecutive failures before opening circuit (default: 5)
        recovery_timeout: Time in seconds to wait before transitioning to HALF_OPEN (default: 60.0)
        success_threshold: Number of consecutive successes needed to close circuit from HALF_OPEN (default: 3)
        call_timeout: Timeout in seconds for individual protected calls (default: 30.0)
        failure_rate_threshold: Failure rate (0.0-1.0) that triggers circuit opening (default: 0.5)
        min_calls_to_evaluate: Minimum calls before evaluating failure rate (default: 10)
        sliding_window_size: Size of sliding window for metrics calculation (default: 100)
        exponential_backoff_multiplier: Multiplier for recovery timeout backoff (default: 2.0)
        max_recovery_timeout: Maximum recovery timeout in seconds (default: 300.0)

    Examples:
        Create basic configuration:

        >>> config = CircuitConfig(
        ...     failure_threshold=3,
        ...     recovery_timeout=30.0
        ... )

        Create configuration for unreliable networks:

        >>> tolerant_config = CircuitConfig(
        ...     failure_threshold=10,          # Allow more failures
        ...     recovery_timeout=120.0,        # Wait longer for recovery
        ...     failure_rate_threshold=0.8,    # Higher threshold
        ...     min_calls_to_evaluate=20       # More data before decisions
        ... )

        Create configuration for fast recovery:

        >>> fast_config = CircuitConfig(
        ...     failure_threshold=2,           # Fail fast
        ...     recovery_timeout=10.0,         # Quick recovery attempts
        ...     success_threshold=1,           # Single success closes circuit
        ...     failure_rate_threshold=0.3     # Low tolerance
        ... )

        Use with circuit breaker:

        >>> config = CircuitConfig(failure_threshold=5)
        >>> circuit = AsyncCircuitBreaker("api-service", config)

    Raises:
        ValueError: If any configuration values are invalid
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3  # Required successes in HALF_OPEN to close
    call_timeout: float = 30.0
    failure_rate_threshold: float = 0.5  # 50% failure rate threshold
    min_calls_to_evaluate: int = 10  # Minimum calls before evaluating failure rate
    sliding_window_size: int = 100  # Size of the sliding window for metrics
    exponential_backoff_multiplier: float = 2.0
    max_recovery_timeout: float = 300.0  # 5 minutes max

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        if self.success_threshold <= 0:
            raise ValueError("success_threshold must be positive")
        if not 0 < self.failure_rate_threshold <= 1:
            raise ValueError("failure_rate_threshold must be between 0 and 1")
        if self.min_calls_to_evaluate <= 0:
            raise ValueError("min_calls_to_evaluate must be positive")


@dataclass
class CallResult:
    """
    Result of a circuit breaker protected call.

    This class captures the outcome and timing information for each
    call made through the circuit breaker, used for metrics calculation
    and failure rate evaluation.

    Attributes:
        timestamp: When the call was made (Unix timestamp)
        success: Whether the call succeeded
        duration: How long the call took in seconds
        error: Exception that occurred (if call failed)

    Examples:
        Access call results in callbacks:

        >>> def on_call_result(result: CallResult):
        ...     if result.success:
        ...         print(f"✅ Call succeeded in {result.duration:.3f}s")
        ...     else:
        ...         print(f"❌ Call failed: {result.error}")
        ...         print(f"   Duration: {result.duration:.3f}s")

        >>> circuit = AsyncCircuitBreaker("service")
        >>> circuit.add_call_callback(on_call_result)
    """

    timestamp: float
    success: bool
    duration: float
    error: Exception | None = None


@dataclass
class CircuitMetrics:
    """
    Comprehensive metrics for circuit breaker performance and behavior.

    These metrics provide insights into circuit breaker operation,
    service performance, and failure patterns. They're useful for
    monitoring, alerting, and performance analysis.

    Attributes:
        total_calls: Total number of calls attempted
        successful_calls: Number of calls that succeeded
        failed_calls: Number of calls that failed
        short_circuited_calls: Number of calls blocked by open circuit
        avg_response_time: Average response time in seconds
        current_failure_rate: Current failure rate (0.0-1.0)
        state_changes: Number of times circuit state changed
        last_state_change: Timestamp of last state change
        time_in_open_state: Total time spent in OPEN state (seconds)

    Properties:
        success_rate: Calculated success rate (0.0-1.0)
        failure_rate: Calculated failure rate (0.0-1.0)

    Examples:
        Monitor circuit performance:

        >>> circuit = AsyncCircuitBreaker("api-service")
        >>>
        >>> # After some operations...
        >>> metrics = circuit.metrics
        >>> print(f"Success rate: {metrics.success_rate:.1%}")
        >>> print(f"Average response time: {metrics.avg_response_time:.3f}s")
        >>> print(f"Circuit state changes: {metrics.state_changes}")

        Check if circuit is performing well:

        >>> metrics = circuit.metrics
        >>> if metrics.success_rate < 0.9:
        ...     print("⚠️ Service performance is degraded")
        >>> if metrics.avg_response_time > 5.0:
        ...     print("⚠️ Service is responding slowly")

        Monitor circuit stability:

        >>> metrics = circuit.metrics
        >>> if metrics.state_changes > 10:
        ...     print("⚠️ Circuit is unstable (frequent state changes)")
        >>> if metrics.time_in_open_state > 300:
        ...     print("⚠️ Service has been down for over 5 minutes")
    """

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    short_circuited_calls: int = 0
    avg_response_time: float = 0.0
    current_failure_rate: float = 0.0
    state_changes: int = 0
    last_state_change: float | None = None
    time_in_open_state: float = 0.0

    @property
    def success_rate(self) -> float:
        """
        Calculate success rate as a percentage.

        Returns:
            Success rate between 0.0 and 1.0 (1.0 = 100% success)
        """
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def failure_rate(self) -> float:
        """
        Calculate failure rate as a percentage.

        Returns:
            Failure rate between 0.0 and 1.0 (0.0 = no failures)
        """
        return 1.0 - self.success_rate


class AsyncCircuitBreaker(Generic[T]):
    """
    High-performance async circuit breaker with advanced features.

    The circuit breaker pattern prevents cascading failures by monitoring
    the health of external services and "opening" when failures exceed
    thresholds, allowing the system to fail fast and recover gracefully.

    Features:
        - State machine with proper CLOSED/OPEN/HALF_OPEN transitions
        - Sliding window failure rate calculation with configurable thresholds
        - Exponential backoff for recovery timeouts
        - Health monitoring with optional proactive health checks
        - Comprehensive metrics collection and monitoring
        - Thread-safe operations with asyncio locks
        - Configurable failure detection strategies
        - Event callbacks for monitoring and alerting
        - Background tasks for health monitoring and cleanup

    Args:
        name: Unique identifier for this circuit breaker instance
        config: Configuration object (uses defaults if None)
        health_checker: Optional health checker for proactive monitoring

    Examples:
        Basic usage with decorator:

        >>> config = CircuitConfig(
        ...     failure_threshold=3,
        ...     recovery_timeout=30.0,
        ...     failure_rate_threshold=0.6
        ... )
        >>>
        >>> circuit = AsyncCircuitBreaker("outline-api", config)
        >>>
        >>> @circuit.protect
        ... async def api_call():
        ...     async with aiohttp.ClientSession() as session:
        ...         async with session.get("https://api.example.com") as response:
        ...             return await response.json()
        >>>
        >>> try:
        ...     result = await api_call()
        ... except CircuitOpenError as e:
        ...     print(f"Circuit open, retry after {e.retry_after} seconds")

        Manual call protection:

        >>> circuit = AsyncCircuitBreaker("database")
        >>>
        >>> async def get_user(user_id: int):
        ...     async def db_query():
        ...         # Your database query here
        ...         return await db.fetch_user(user_id)
        ...
        ...     try:
        ...         return await circuit.call(db_query)
        ...     except CircuitOpenError:
        ...         # Return cached data or default
        ...         return get_cached_user(user_id)

        Context manager protection:

        >>> circuit = AsyncCircuitBreaker("external-service")
        >>>
        >>> async def process_data():
        ...     try:
        ...         async with circuit.protect_context():
        ...             # Multiple operations protected together
        ...             data = await fetch_external_data()
        ...             result = await process_external_data(data)
        ...             await save_result(result)
        ...             return result
        ...     except CircuitOpenError:
        ...         print("External service unavailable")
        ...         return None

        With health monitoring:

        >>> class ServiceHealthChecker:
        ...     async def check_health(self) -> bool:
        ...         try:
        ...             async with aiohttp.ClientSession() as session:
        ...                 async with session.get("https://api.example.com/health") as response:
        ...                     return response.status == 200
        ...         except:
        ...             return False
        >>>
        >>> health_checker = ServiceHealthChecker()
        >>> circuit = AsyncCircuitBreaker(
        ...     "api-service",
        ...     health_checker=health_checker
        ... )
        >>>
        >>> async with circuit:
        ...     # Circuit will proactively monitor health
        ...     result = await circuit.call(api_call)

        Monitor circuit performance:

        >>> circuit = AsyncCircuitBreaker("service")
        >>>
        >>> def on_state_change(old_state, new_state):
        ...     print(f"Circuit state: {old_state.name} -> {new_state.name}")
        >>>
        >>> def on_call_result(result):
        ...     if not result.success:
        ...         print(f"Call failed: {result.error}")
        >>>
        >>> circuit.add_state_change_callback(on_state_change)
        >>> circuit.add_call_callback(on_call_result)
        >>>
        >>> async with circuit:
        ...     # Perform operations with monitoring
        ...     for i in range(10):
        ...         try:
        ...             await circuit.call(some_operation)
        ...         except CircuitOpenError:
        ...             print(f"Circuit open on attempt {i+1}")
        ...             break

        Production monitoring setup:

        >>> import asyncio
        >>>
        >>> async def monitor_circuit_health():
        ...     circuit = AsyncCircuitBreaker("critical-service")
        ...
        ...     def alert_on_state_change(old_state, new_state):
        ...         if new_state == CircuitState.OPEN:
        ...             # Send alert to monitoring system
        ...             send_alert(f"Circuit breaker opened for critical-service")
        ...         elif new_state == CircuitState.CLOSED:
        ...             send_alert(f"Critical-service recovered")
        ...
        ...     circuit.add_state_change_callback(alert_on_state_change)
        ...
        ...     async with circuit:
        ...         while True:
        ...             metrics = circuit.metrics
        ...
        ...             # Log metrics every minute
        ...             print(f"Success rate: {metrics.success_rate:.1%}")
        ...             print(f"Response time: {metrics.avg_response_time:.3f}s")
        ...
        ...             # Check for performance degradation
        ...             if metrics.success_rate < 0.95:
        ...                 send_warning("Service performance degraded")
        ...
        ...             await asyncio.sleep(60)

    Raises:
        CircuitOpenError: When circuit is open and calls are blocked
        ValueError: If configuration parameters are invalid
    """

    def __init__(
        self,
        name: str,
        config: CircuitConfig | None = None,
        health_checker: HealthChecker | None = None,
    ) -> None:
        self.name = name
        self.config = config or CircuitConfig()
        self._health_checker = health_checker

        # State management
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._state_change_time = time.time()
        self._lock = asyncio.Lock()

        # Sliding window for call results
        self._call_history: Deque[CallResult] = deque(
            maxlen=self.config.sliding_window_size
        )

        # Metrics and monitoring
        self._metrics = CircuitMetrics()
        self._backoff_count = 0

        # Event callbacks
        self._state_change_callbacks: WeakSet[
            Callable[[CircuitState, CircuitState], None]
        ] = WeakSet()
        self._call_callbacks: WeakSet[Callable[[CallResult], None]] = WeakSet()

        # Background tasks
        self._health_check_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

        logger.info(f"Circuit breaker '{name}' initialized with config: {config}")

    async def __aenter__(self) -> AsyncCircuitBreaker[T]:
        """
        Start circuit breaker with background tasks.

        This method initializes all background monitoring and cleanup tasks.
        It's called when entering an 'async with' block.

        Returns:
            The circuit breaker instance

        Examples:
            Use as context manager:

            >>> circuit = AsyncCircuitBreaker("service")
            >>> async with circuit:
            ...     # Circuit is now active with background tasks
            ...     result = await circuit.call(some_function)
        """
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Stop circuit breaker and cleanup resources.

        This method stops all background tasks and cleans up resources.
        It's called when exiting an 'async with' block.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        await self.stop()

    async def start(self) -> None:
        """
        Start background monitoring tasks.

        This method starts the health monitoring and metrics cleanup tasks.
        It's automatically called when using the circuit breaker as a context
        manager, but can be called manually if needed.

        Examples:
            Manual start/stop:

            >>> circuit = AsyncCircuitBreaker("service")
            >>> await circuit.start()
            >>> try:
            ...     result = await circuit.call(some_function)
            ... finally:
            ...     await circuit.stop()
        """
        if self._running:
            return

        self._running = True

        # Start health monitoring if health checker is provided
        if self._health_checker:
            self._health_check_task = asyncio.create_task(self._health_monitor())

        # Start cleanup task for old call history
        self._cleanup_task = asyncio.create_task(self._cleanup_old_calls())

        logger.info(f"Circuit breaker '{self.name}' started")

    async def stop(self) -> None:
        """
        Stop background tasks and cleanup.

        This method stops all background monitoring tasks and cleans up
        resources. It should be called when the circuit breaker is no
        longer needed.

        Examples:
            Manual cleanup:

            >>> circuit = AsyncCircuitBreaker("service")
            >>> await circuit.start()
            >>> # ... use circuit ...
            >>> await circuit.stop()  # Clean shutdown
        """
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Circuit breaker '{self.name}' stopped")

    @property
    def state(self) -> CircuitState:
        """
        Get current circuit state.

        Returns:
            Current state (CLOSED, OPEN, or HALF_OPEN)

        Examples:
            Check circuit state:

            >>> circuit = AsyncCircuitBreaker("service")
            >>> if circuit.state == CircuitState.OPEN:
            ...     print("Service is currently unavailable")
            >>> elif circuit.state == CircuitState.HALF_OPEN:
            ...     print("Service is being tested for recovery")
        """
        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        """
        Get current metrics (returns a copy to prevent external modification).

        Returns:
            Current circuit breaker metrics

        Examples:
            Monitor performance:

            >>> circuit = AsyncCircuitBreaker("service")
            >>> metrics = circuit.metrics
            >>> print(f"Success rate: {metrics.success_rate:.1%}")
            >>> print(f"Average response time: {metrics.avg_response_time:.3f}s")
            >>> print(f"Total calls: {metrics.total_calls}")
        """
        # Create a copy to prevent external modification
        return CircuitMetrics(
            total_calls=self._metrics.total_calls,
            successful_calls=self._metrics.successful_calls,
            failed_calls=self._metrics.failed_calls,
            short_circuited_calls=self._metrics.short_circuited_calls,
            avg_response_time=self._metrics.avg_response_time,
            current_failure_rate=self._calculate_failure_rate(),
            state_changes=self._metrics.state_changes,
            last_state_change=self._metrics.last_state_change,
            time_in_open_state=self._metrics.time_in_open_state,
        )

    @property
    def health_checker(self) -> HealthChecker | None:
        """
        Get current health checker.

        Returns:
            Current health checker instance or None
        """
        return self._health_checker

    @health_checker.setter
    def health_checker(self, checker: HealthChecker | None) -> None:
        """
        Set health checker.

        Args:
            checker: New health checker instance or None to disable

        Examples:
            Update health checker:

            >>> circuit = AsyncCircuitBreaker("service")
            >>> circuit.health_checker = MyCustomHealthChecker()
        """
        self._health_checker = checker

    def add_state_change_callback(
        self, callback: Callable[[CircuitState, CircuitState], None]
    ) -> None:
        """
        Add callback for state changes.

        The callback will be called whenever the circuit breaker changes
        state (e.g., from CLOSED to OPEN). This is useful for monitoring,
        alerting, and logging.

        Args:
            callback: Function that takes (old_state, new_state) parameters

        Examples:
            Add logging callback:

            >>> def log_state_changes(old_state, new_state):
            ...     logger.info(f"Circuit {circuit.name}: {old_state.name} -> {new_state.name}")
            >>>
            >>> circuit = AsyncCircuitBreaker("service")
            >>> circuit.add_state_change_callback(log_state_changes)

            Add alerting callback:

            >>> def alert_on_open(old_state, new_state):
            ...     if new_state == CircuitState.OPEN:
            ...         send_alert(f"Service {circuit.name} is down")
            ...     elif old_state == CircuitState.OPEN and new_state == CircuitState.CLOSED:
            ...         send_alert(f"Service {circuit.name} recovered")
            >>>
            >>> circuit.add_state_change_callback(alert_on_open)
        """
        self._state_change_callbacks.add(callback)

    def add_call_callback(self, callback: Callable[[CallResult], None]) -> None:
        """
        Add callback for call results.

        The callback will be called for every protected call with the
        result information. This is useful for detailed monitoring,
        performance tracking, and debugging.

        Args:
            callback: Function that takes a CallResult parameter

        Examples:
            Add performance monitoring:

            >>> def monitor_performance(result: CallResult):
            ...     if result.duration > 5.0:
            ...         logger.warning(f"Slow call: {result.duration:.3f}s")
            ...     if not result.success:
            ...         logger.error(f"Call failed: {result.error}")
            >>>
            >>> circuit = AsyncCircuitBreaker("service")
            >>> circuit.add_call_callback(monitor_performance)

            Add metrics collection:

            >>> response_times = []
            >>>
            >>> def collect_metrics(result: CallResult):
            ...     response_times.append(result.duration)
            ...     if len(response_times) > 100:
            ...         response_times.pop(0)  # Keep last 100
            >>>
            >>> circuit.add_call_callback(collect_metrics)
        """
        self._call_callbacks.add(callback)

    def protect(self, func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        """
        Decorator to protect async functions with circuit breaker.

        This decorator wraps an async function so that all calls to it
        are protected by the circuit breaker. It's the most convenient
        way to add circuit breaker protection to existing functions.

        Args:
            func: Async function to protect

        Returns:
            Protected async function with same signature

        Examples:
            Protect an API call:

            >>> circuit = AsyncCircuitBreaker("external-api")
            >>>
            >>> @circuit.protect
            ... async def call_external_api(endpoint: str) -> dict:
            ...     async with aiohttp.ClientSession() as session:
            ...         async with session.get(f"https://api.example.com/{endpoint}") as response:
            ...             return await response.json()
            >>>
            >>> try:
            ...     data = await call_external_api("users/123")
            ... except CircuitOpenError as e:
            ...     print(f"API unavailable, retry after {e.retry_after}s")

            Protect a database operation:

            >>> db_circuit = AsyncCircuitBreaker("database")
            >>>
            >>> @db_circuit.protect
            ... async def get_user_from_db(user_id: int) -> User:
            ...     async with database.transaction():
            ...         return await database.fetch_user(user_id)
            >>>
            >>> try:
            ...     user = await get_user_from_db(123)
            ... except CircuitOpenError:
            ...     # Fallback to cache
            ...     user = await get_user_from_cache(123)

            Multiple protected functions:

            >>> api_circuit = AsyncCircuitBreaker("api")
            >>>
            >>> @api_circuit.protect
            ... async def get_data():
            ...     return await api_call("/data")
            >>>
            >>> @api_circuit.protect
            ... async def post_data(data):
            ...     return await api_call("/data", method="POST", json=data)
            >>>
            >>> # Both functions share the same circuit breaker state
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await self.call(func, *args, **kwargs)

        return wrapper

    @asynccontextmanager
    async def protect_context(self):
        """
        Context manager for protecting code blocks.

        This context manager allows you to protect multiple operations
        together as a single unit. If any operation fails, the entire
        context is considered failed for circuit breaker purposes.

        Yields:
            Nothing - the context itself provides the protection

        Examples:
            Protect multiple related operations:

            >>> circuit = AsyncCircuitBreaker("service")
            >>>
            >>> async def process_order(order_id: str):
            ...     try:
            ...         async with circuit.protect_context():
            ...             # All these operations are protected together
            ...             order = await fetch_order(order_id)
            ...             payment = await process_payment(order.payment_info)
            ...             inventory = await update_inventory(order.items)
            ...             await send_confirmation(order.customer_email)
            ...             return {"order": order, "payment": payment}
            ...     except CircuitOpenError:
            ...         return {"error": "Service temporarily unavailable"}

            Protect batch operations:

            >>> async def sync_users():
            ...     try:
            ...         async with circuit.protect_context():
            ...             users = await fetch_all_users()
            ...             for user in users:
            ...                 await update_user_profile(user)
            ...                 await sync_user_permissions(user)
            ...             await commit_changes()
            ...     except CircuitOpenError:
            ...         logger.warning("User sync skipped - service unavailable")

            Conditional protection:

            >>> async def optional_enhancement(data):
            ...     # Core processing always happens
            ...     result = await process_core_data(data)
            ...
            ...     # Enhancement is optional and protected
            ...     try:
            ...         async with circuit.protect_context():
            ...             enhancement = await enhance_data(result)
            ...             result.update(enhancement)
            ...     except CircuitOpenError:
            ...         logger.info("Enhancement service unavailable, using basic result")
            ...
            ...     return result
        """
        await self._check_state()

        start_time = time.time()
        error: Exception | None = None

        try:
            yield
            # Success case
            duration = time.time() - start_time
            await self._record_success(duration)

        except Exception as e:
            # Failure case
            duration = time.time() - start_time
            error = e
            await self._record_failure(duration, e)
            raise

    async def call(
        self, func: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """
        Execute function with circuit breaker protection.

        This method executes an async function with full circuit breaker
        protection, including state checking, timeout handling, and
        result recording for metrics.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitOpenError: When circuit is open and calls are blocked
            asyncio.TimeoutError: When call exceeds configured timeout
            Exception: Original exception from the function (if not circuit-related)

        Examples:
            Execute a simple function:

            >>> circuit = AsyncCircuitBreaker("service")
            >>>
            >>> async def fetch_data():
            ...     # Some async operation
            ...     return {"data": "value"}
            >>>
            >>> try:
            ...     result = await circuit.call(fetch_data)
            ...     print(f"Got result: {result}")
            ... except CircuitOpenError as e:
            ...     print(f"Circuit open, retry after {e.retry_after}s")

            Execute function with arguments:

            >>> async def process_user(user_id: int, action: str):
            ...     # Process user with given action
            ...     return f"Processed user {user_id} with {action}"
            >>>
            >>> try:
            ...     result = await circuit.call(process_user, 123, action="update")
            ...     print(result)
            ... except CircuitOpenError:
            ...     print("Service unavailable")

            Handle different exception types:

            >>> async def risky_operation():
            ...     if random.random() < 0.5:
            ...         raise ValueError("Random failure")
            ...     return "success"
            >>>
            >>> try:
            ...     result = await circuit.call(risky_operation)
            ... except CircuitOpenError:
            ...     print("Circuit is open")
            ... except ValueError as e:
            ...     print(f"Operation failed: {e}")
            ... except asyncio.TimeoutError:
            ...     print("Operation timed out")

            With retry logic:

            >>> async def call_with_retry(operation, max_retries=3):
            ...     for attempt in range(max_retries):
            ...         try:
            ...             return await circuit.call(operation)
            ...         except CircuitOpenError as e:
            ...             if attempt == max_retries - 1:
            ...                 raise
            ...             await asyncio.sleep(e.retry_after)
            ...         except Exception as e:
            ...             if attempt == max_retries - 1:
            ...                 raise
            ...             await asyncio.sleep(1.0)  # Brief delay before retry
        """
        await self._check_state()

        start_time = time.time()

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs), timeout=self.config.call_timeout
            )

            # Record success
            duration = time.time() - start_time
            await self._record_success(duration)

            return result

        except Exception as e:
            # Record failure
            duration = time.time() - start_time
            await self._record_failure(duration, e)
            raise

    async def reset(self) -> None:
        """
        Manually reset circuit breaker to CLOSED state.

        This method forces the circuit breaker to the CLOSED state,
        clearing all failure history and metrics. It's useful for
        manual recovery or testing scenarios.

        Examples:
            Manual recovery after maintenance:

            >>> circuit = AsyncCircuitBreaker("service")
            >>>
            >>> # After service maintenance is complete
            >>> await circuit.reset()
            >>> print("Circuit breaker reset - service should be available")

            Testing scenarios:

            >>> async def test_circuit_behavior():
            ...     circuit = AsyncCircuitBreaker("test-service")
            ...
            ...     # Cause some failures to open circuit
            ...     for _ in range(5):
            ...         try:
            ...             await circuit.call(failing_function)
            ...         except:
            ...             pass
            ...
            ...     assert circuit.state == CircuitState.OPEN
            ...
            ...     # Reset for next test
            ...     await circuit.reset()
            ...     assert circuit.state == CircuitState.CLOSED

            Emergency recovery:

            >>> async def emergency_reset():
            ...     # In case of emergency, force circuit closed
            ...     await circuit.reset()
            ...     logger.warning("Circuit breaker manually reset")
        """
        async with self._lock:
            await self._transition_to(CircuitState.CLOSED)
            self._call_history.clear()
            self._metrics = CircuitMetrics()

        logger.info(f"Circuit breaker '{self.name}' manually reset")

    async def force_open(self) -> None:
        """
        Manually force circuit breaker to OPEN state.

        This method forces the circuit breaker to the OPEN state,
        causing all subsequent calls to fail fast. It's useful for
        maintenance scenarios or emergency shutdowns.

        Examples:
            Maintenance mode:

            >>> circuit = AsyncCircuitBreaker("service")
            >>>
            >>> # Before starting maintenance
            >>> await circuit.force_open()
            >>> print("Service maintenance mode - all calls will be blocked")
            >>>
            >>> # Perform maintenance...
            >>>
            >>> # After maintenance
            >>> await circuit.reset()

            Emergency shutdown:

            >>> async def emergency_shutdown():
            ...     # Force all circuits open during emergency
            ...     for circuit in all_circuits:
            ...         await circuit.force_open()
            ...     logger.critical("All services forced offline for emergency")

            Testing failure scenarios:

            >>> async def test_fallback_behavior():
            ...     circuit = AsyncCircuitBreaker("test-service")
            ...
            ...     # Force circuit open to test fallback
            ...     await circuit.force_open()
            ...
            ...     try:
            ...         result = await circuit.call(some_function)
            ...     except CircuitOpenError:
            ...         # Test that fallback works correctly
            ...         result = get_fallback_data()
            ...
            ...     assert result is not None
        """
        async with self._lock:
            await self._transition_to(CircuitState.OPEN)
            self._last_failure_time = time.time()

        logger.info(f"Circuit breaker '{self.name}' manually opened")

    def __repr__(self) -> str:
        """
        String representation of the circuit breaker.

        Returns:
            Detailed string representation including current state and metrics

        Examples:
            Display circuit status:

            >>> circuit = AsyncCircuitBreaker("api-service")
            >>> print(repr(circuit))
            # Output: AsyncCircuitBreaker(name='api-service', state=CLOSED, calls=0, failure_rate=0.00%)

            Monitor multiple circuits:

            >>> circuits = [
            ...     AsyncCircuitBreaker("database"),
            ...     AsyncCircuitBreaker("cache"),
            ...     AsyncCircuitBreaker("api")
            ... ]
            >>>
            >>> for circuit in circuits:
            ...     print(repr(circuit))
        """
        return (
            f"AsyncCircuitBreaker(name='{self.name}', "
            f"state={self._state.name}, "
            f"calls={self._metrics.total_calls}, "
            f"failure_rate={self._calculate_failure_rate():.2%})"
        )

    # Private methods for internal circuit breaker logic

    async def _check_state(self) -> None:
        """Check current state and transition if needed."""
        async with self._lock:
            current_time = time.time()

            if self._state == CircuitState.OPEN:
                recovery_timeout = self._calculate_recovery_timeout()

                if current_time - self._last_failure_time >= recovery_timeout:
                    await self._transition_to(CircuitState.HALF_OPEN)
                else:
                    # Circuit is still open
                    retry_after = recovery_timeout - (
                        current_time - self._last_failure_time
                    )
                    self._metrics.short_circuited_calls += 1
                    raise CircuitOpenError(
                        f"Circuit breaker '{self.name}' is OPEN", retry_after
                    )

            elif self._state == CircuitState.HALF_OPEN:
                # In half-open state, allow calls but monitor closely
                pass

            elif self._state == CircuitState.CLOSED:
                # Check if we should open the circuit
                if await self._should_open_circuit():
                    await self._transition_to(CircuitState.OPEN)
                    retry_after = self._calculate_recovery_timeout()
                    self._metrics.short_circuited_calls += 1
                    raise CircuitOpenError(
                        f"Circuit breaker '{self.name}' opened due to failures",
                        retry_after,
                    )

    async def _record_success(self, duration: float) -> None:
        """Record a successful call."""
        async with self._lock:
            call_result = CallResult(
                timestamp=time.time(), success=True, duration=duration
            )

            self._call_history.append(call_result)
            self._update_metrics(call_result)

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)

            # Notify callbacks
            for callback in list(self._call_callbacks):
                try:
                    callback(call_result)
                except Exception as e:
                    logger.warning(f"Callback error: {e}")

    async def _record_failure(self, duration: float, error: Exception) -> None:
        """Record a failed call."""
        async with self._lock:
            call_result = CallResult(
                timestamp=time.time(), success=False, duration=duration, error=error
            )

            self._call_history.append(call_result)
            self._update_metrics(call_result)

            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open immediately opens the circuit
                await self._transition_to(CircuitState.OPEN)

            # Notify callbacks
            for callback in list(self._call_callbacks):
                try:
                    callback(call_result)
                except Exception as e:
                    logger.warning(f"Callback error: {e}")

    async def _should_open_circuit(self) -> bool:
        """Determine if circuit should be opened."""
        if len(self._call_history) < self.config.min_calls_to_evaluate:
            return False

        failure_rate = self._calculate_failure_rate()

        return (
            failure_rate >= self.config.failure_rate_threshold
            or self._failure_count >= self.config.failure_threshold
        )

    def _calculate_failure_rate(self) -> float:
        """Calculate current failure rate from sliding window."""
        if not self._call_history:
            return 0.0

        recent_window = list(self._call_history)[-self.config.min_calls_to_evaluate :]
        if len(recent_window) < self.config.min_calls_to_evaluate:
            return 0.0

        failed_calls = sum(1 for call in recent_window if not call.success)
        return failed_calls / len(recent_window)

    def _calculate_recovery_timeout(self) -> float:
        """Calculate recovery timeout with exponential backoff."""
        timeout = self.config.recovery_timeout * (
            self.config.exponential_backoff_multiplier**self._backoff_count
        )
        return min(timeout, self.config.max_recovery_timeout)

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state

        if old_state == new_state:
            return

        # Update state
        self._state = new_state
        current_time = time.time()

        # Update metrics
        if self._metrics.last_state_change:
            if old_state == CircuitState.OPEN:
                self._metrics.time_in_open_state += (
                    current_time - self._metrics.last_state_change
                )

        self._metrics.state_changes += 1
        self._metrics.last_state_change = current_time
        self._state_change_time = current_time

        # Reset counters based on transition
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._backoff_count = 0
        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            self._backoff_count += 1
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._failure_count = 0

        logger.info(
            f"Circuit breaker '{self.name}' transitioned: {old_state.name} -> {new_state.name}"
        )

        # Notify callbacks
        for callback in list(self._state_change_callbacks):
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.warning(f"State change callback error: {e}")

    def _update_metrics(self, call_result: CallResult) -> None:
        """Update internal metrics."""
        self._metrics.total_calls += 1

        if call_result.success:
            self._metrics.successful_calls += 1
        else:
            self._metrics.failed_calls += 1

        # Update average response time (exponential moving average)
        alpha = 0.1  # Smoothing factor
        if self._metrics.avg_response_time == 0:
            self._metrics.avg_response_time = call_result.duration
        else:
            self._metrics.avg_response_time = (
                alpha * call_result.duration
                + (1 - alpha) * self._metrics.avg_response_time
            )

    async def _health_monitor(self) -> None:
        """Background task for health monitoring."""
        while self._running:
            try:
                if self._state == CircuitState.OPEN and self._health_checker:
                    is_healthy = await self._health_checker.check_health()
                    if is_healthy:
                        async with self._lock:
                            await self._transition_to(CircuitState.HALF_OPEN)

                # Health check interval
                await asyncio.sleep(30.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Health monitor error: {e}")
                await asyncio.sleep(5.0)

    async def _cleanup_old_calls(self) -> None:
        """Background task to cleanup old call history."""
        while self._running:
            try:
                current_time = time.time()
                cutoff_time = current_time - 300.0  # Keep last 5 minutes

                async with self._lock:
                    # Remove old calls (deque automatically maintains max size)
                    while (
                        self._call_history
                        and self._call_history[0].timestamp < cutoff_time
                    ):
                        self._call_history.popleft()

                await asyncio.sleep(60.0)  # Cleanup every minute

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Cleanup task error: {e}")
                await asyncio.sleep(10.0)
