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
import time
from dataclasses import dataclass
from typing import Final

from pyoutlineapi.exceptions import APIError


@dataclass(slots=True, frozen=True)
class TokenBucketConfig:
    """Immutable configuration for token bucket."""

    rate_per_second: int
    capacity: int


@dataclass(slots=True)
class TokenBucket:
    """Token bucket for rate limiting using integer arithmetic."""

    config: TokenBucketConfig
    _tokens: int
    _last_update_ns: int = 0  # Store time in nanoseconds for better precision

    NANOS_IN_SECOND: Final[int] = 1_000_000_000

    @classmethod
    def create(cls, rate_per_second: int, capacity: int) -> TokenBucket:
        """Create a new token bucket with integer parameters."""
        if rate_per_second <= 0:
            raise ValueError("Rate must be positive")
        if capacity <= 0:
            raise ValueError("Capacity must be positive")

        config = TokenBucketConfig(rate_per_second=rate_per_second, capacity=capacity)
        return cls(
            config=config,
            _tokens=capacity,
            _last_update_ns=time.monotonic_ns(),
        )

    def update(self) -> None:
        """Update the number of tokens based on elapsed time."""
        now_ns = time.monotonic_ns()
        delta_ns = now_ns - self._last_update_ns

        # Convert nanoseconds to tokens
        new_tokens = (delta_ns * self.config.rate_per_second) // self.NANOS_IN_SECOND

        if new_tokens > 0:
            self._tokens = min(self.config.capacity, self._tokens + new_tokens)
            self._last_update_ns = now_ns

    async def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire (must be positive integer)

        Returns:
            Time to wait in seconds before the request can be made

        Raises:
            ValueError: If tokens is not positive
        """
        if tokens <= 0:
            raise ValueError("Token count must be positive")

        if tokens > self.config.capacity:
            raise ValueError("Requested tokens exceed bucket capacity")

        self.update()

        if self._tokens >= tokens:
            self._tokens -= tokens
            return 0.0

        # Calculate wait time in seconds
        missing_tokens = tokens - self._tokens
        return missing_tokens / self.config.rate_per_second


class RateLimiter:
    """Memory-efficient rate limiter using integer token bucket algorithm."""

    __slots__ = ("_buckets", "_default_config", "_lock")

    def __init__(
        self,
        rate_per_second: int = 10,
        burst: int = 20,
    ) -> None:
        self._default_config = TokenBucketConfig(
            rate_per_second=rate_per_second, capacity=burst
        )
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

    def get_bucket(self, key: str = "default") -> TokenBucket:
        """Get or create a token bucket for the given key."""
        if key not in self._buckets:
            self._buckets[key] = TokenBucket.create(
                rate_per_second=self._default_config.rate_per_second,
                capacity=self._default_config.capacity,
            )
        return self._buckets[key]

    async def acquire(
        self, key: str = "default", tokens: int = 1, wait: bool = True
    ) -> bool:
        """
        Acquire permission to make a request.

        Args:
            key: Rate limit key (e.g., endpoint name)
            tokens: Number of tokens to acquire
            wait: Whether to wait if tokens are not available

        Returns:
            True if tokens were acquired, False if not available and wait=False

        Raises:
            ValueError: If tokens is not positive
        """
        if tokens <= 0:
            raise ValueError("Token count must be positive")

        async with self._lock:
            bucket = self.get_bucket(key)
            wait_time = await bucket.acquire(tokens)

            if wait_time <= 0:
                return True

            if not wait:
                return False

            await asyncio.sleep(wait_time)
            return True


def rate_limit(
    rate_per_second: int | None = None,
    burst: int | None = None,
    key: str | None = None,
    wait: bool = True,
):
    """
    Decorator for rate-limiting API methods.

    Args:
        rate_per_second: Requests per second (defaults to client's rate)
        burst: Maximum burst size (defaults to client's burst)
        key: Rate limit key (defaults to method name)
        wait: Whether to wait for tokens or fail immediately
    """

    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            if not hasattr(self, "_rate_limiter"):
                self._rate_limiter = RateLimiter(
                    rate_per_second=rate_per_second or self._default_rate,
                    burst=burst or self._default_burst,
                )

            limit_key = key or func.__name__

            try:
                acquired = await self._rate_limiter.acquire(key=limit_key, wait=wait)
            except ValueError as e:
                raise APIError(f"Rate limit error: {e}") from e

            if not acquired:
                raise APIError("Rate limit exceeded")

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator
