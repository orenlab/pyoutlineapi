"""
PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
Full license text: https://opensource.org/licenses/MIT
Source repository: https://github.com/orenlab/pyoutlineapi

Module: Batch operations addon (optional).

This module provides efficient batch processing of multiple operations
with concurrency control and error handling.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .common_types import Validators

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .client import AsyncOutlineClient
    from .models import AccessKey

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class BatchResult:
    """
    Result of batch operation.

    Contains statistics and results from a batch operation,
    including both successful and failed operations.
    """

    total: int
    successful: int
    failed: int
    results: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """
        Calculate success rate.

        Returns:
            float: Success rate (0.0 to 1.0)

        Example:
            >>> result = await batch.create_multiple_keys(configs)
            >>> print(f"Success rate: {result.success_rate:.2%}")
        """
        if self.total == 0:
            return 1.0
        return self.successful / self.total

    @property
    def has_errors(self) -> bool:
        """
        Check if any operations failed.

        Returns:
            bool: True if at least one operation failed
        """
        return self.failed > 0

    def get_successful_results(self) -> list[Any]:
        """
        Get only successful results.

        Returns:
            list: List of successful results (excludes exceptions)

        Example:
            >>> result = await batch.create_multiple_keys(configs)
            >>> for key in result.get_successful_results():
            ...     print(f"Created: {key.name}")
        """
        return [r for r in self.results if not isinstance(r, Exception)]

    def get_failures(self) -> list[Exception]:
        """
        Get only failures.

        Returns:
            list: List of exceptions from failed operations

        Example:
            >>> result = await batch.delete_multiple_keys(key_ids)
            >>> for error in result.get_failures():
            ...     print(f"Error: {error}")
        """
        return [r for r in self.results if isinstance(r, Exception)]


class BatchProcessor(Generic[T, R]):
    """
    Generic batch processor with concurrency control.

    Processes items in parallel with configurable concurrency limit.
    """

    def __init__(self, max_concurrent: int = 5) -> None:
        """
        Initialize batch processor.

        Args:
            max_concurrent: Maximum concurrent operations (default: 5)
        """
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def process(
        self,
        items: list[T],
        processor: Callable[[T], Awaitable[R]],
        *,
        fail_fast: bool = False,
    ) -> list[R | Exception]:
        """
        Process items in batch with concurrency control.

        Args:
            items: Items to process
            processor: Async function to process each item
            fail_fast: Stop on first error if True (default: False)

        Returns:
            list: Results or exceptions for each item
        """

        async def process_single(item: T) -> R | Exception:
            async with self._semaphore:
                try:
                    return await processor(item)
                except Exception as e:
                    if fail_fast:
                        raise
                    return e

        tasks = [process_single(item) for item in items]
        return await asyncio.gather(*tasks, return_exceptions=not fail_fast)


class BatchOperations:
    """
    Batch operations addon for AsyncOutlineClient.

    Features:
    - Concurrent batch operations with configurable limits
    - Error handling (fail-fast or continue on errors)
    - Validation error tracking
    - Progress monitoring

    Example:
        >>> from pyoutlineapi import AsyncOutlineClient
        >>> from pyoutlineapi.batch_operations import BatchOperations
        >>>
        >>> async with AsyncOutlineClient.from_env() as client:
        ...     batch = BatchOperations(client, max_concurrent=10)
        ...
        ...     # Create multiple keys
        ...     configs = [
        ...         {"name": "User1"},
        ...         {"name": "User2"},
        ...         {"name": "User3"},
        ...     ]
        ...     result = await batch.create_multiple_keys(configs)
        ...     print(f"Created {result.successful}/{result.total} keys")
    """

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        max_concurrent: int = 5,
    ) -> None:
        """
        Initialize batch operations.

        Args:
            client: Outline client instance
            max_concurrent: Maximum concurrent operations (default: 5)

        Example:
            >>> async with AsyncOutlineClient.from_env() as client:
            ...     batch = BatchOperations(client, max_concurrent=10)
        """
        self._client = client
        self._processor = BatchProcessor(max_concurrent)

    async def create_multiple_keys(
        self,
        configs: list[dict[str, Any]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """
        Create multiple access keys in batch.

        Args:
            configs: List of key configurations (dicts with name, port, limit, etc.)
            fail_fast: Stop on first error (default: False)

        Returns:
            BatchResult: Operation results with statistics

        Example:
            >>> configs = [
            ...     {"name": "Alice"},
            ...     {"name": "Bob", "port": 8388},
            ...     {"name": "Charlie", "limit": DataLimit(bytes=1024**3)},
            ... ]
            >>> result = await batch.create_multiple_keys(configs)
            >>> print(f"Created: {result.successful}/{result.total}")
            >>> if result.has_errors:
            ...     for error in result.get_failures():
            ...         print(f"Error: {error}")
        """

        async def create_key(config: dict[str, Any]) -> AccessKey:
            return await self._client.create_access_key(**config)

        results = await self._processor.process(
            configs, create_key, fail_fast=fail_fast
        )

        return self._build_result(results)

    async def delete_multiple_keys(
        self,
        key_ids: list[str],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """
        Delete multiple access keys in batch.

        Args:
            key_ids: List of key IDs to delete
            fail_fast: Stop on first error (default: False)

        Returns:
            BatchResult: Operation results with statistics

        Example:
            >>> key_ids = ["key1", "key2", "key3"]
            >>> result = await batch.delete_multiple_keys(key_ids)
            >>> print(f"Deleted: {result.successful}/{result.total}")
        """
        validated_ids: list[str] = []
        validation_errors: list[Exception] = []

        for key_id in key_ids:
            try:
                validated_id = Validators.validate_key_id(key_id)
                validated_ids.append(validated_id)
            except ValueError as e:
                if fail_fast:
                    raise
                # Track validation error
                validation_errors.append(e)

        # Process only validated IDs
        async def delete_key(key_id: str) -> bool:
            return await self._client.delete_access_key(key_id)

        process_results = await self._processor.process(
            validated_ids, delete_key, fail_fast=fail_fast
        )

        # Combine validation errors with process errors
        all_results = validation_errors + process_results

        return self._build_result(all_results)

    async def rename_multiple_keys(
        self,
        key_name_pairs: list[tuple[str, str]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """
        Rename multiple access keys in batch.

        Args:
            key_name_pairs: List of (key_id, new_name) tuples
            fail_fast: Stop on first error (default: False)

        Returns:
            BatchResult: Operation results with statistics

        Example:
            >>> pairs = [
            ...     ("key1", "Alice"),
            ...     ("key2", "Bob"),
            ...     ("key3", "Charlie"),
            ... ]
            >>> result = await batch.rename_multiple_keys(pairs)
            >>> print(f"Renamed: {result.successful}/{result.total}")
        """

        async def rename_key(pair: tuple[str, str]) -> bool:
            key_id, name = pair
            return await self._client.rename_access_key(key_id, name)

        results = await self._processor.process(
            key_name_pairs,
            rename_key,
            fail_fast=fail_fast,
        )

        return self._build_result(results)

    async def set_multiple_data_limits(
        self,
        key_limit_pairs: list[tuple[str, int]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """
        Set data limits for multiple keys in batch.

        Args:
            key_limit_pairs: List of (key_id, bytes_limit) tuples
            fail_fast: Stop on first error (default: False)

        Returns:
            BatchResult: Operation results with statistics

        Example:
            >>> pairs = [
            ...     ("key1", 1024**3),    # 1 GB
            ...     ("key2", 2*1024**3),  # 2 GB
            ...     ("key3", 5*1024**3),  # 5 GB
            ... ]
            >>> result = await batch.set_multiple_data_limits(pairs)
            >>> print(f"Updated: {result.successful}/{result.total}")
        """

        async def set_limit(pair: tuple[str, int]) -> bool:
            key_id, bytes_limit = pair
            return await self._client.set_access_key_data_limit(key_id, bytes_limit)

        results = await self._processor.process(
            key_limit_pairs,
            set_limit,
            fail_fast=fail_fast,
        )

        return self._build_result(results)

    async def fetch_multiple_keys(
        self,
        key_ids: list[str],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """
        Fetch multiple access keys in batch.

        Args:
            key_ids: List of key IDs to fetch
            fail_fast: Stop on first error (default: False)

        Returns:
            BatchResult: Operation results with key objects

        Example:
            >>> key_ids = ["key1", "key2", "key3"]
            >>> result = await batch.fetch_multiple_keys(key_ids)
            >>> for key in result.get_successful_results():
            ...     print(f"{key.name}: {key.access_url}")
        """

        async def fetch_key(key_id: str) -> AccessKey:
            return await self._client.get_access_key(key_id)

        results = await self._processor.process(key_ids, fetch_key, fail_fast=fail_fast)

        return self._build_result(results)

    async def execute_custom_operations(
        self,
        operations: list[Callable[[], Awaitable[Any]]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """
        Execute custom batch operations.

        Args:
            operations: List of async callables (no arguments)
            fail_fast: Stop on first error (default: False)

        Returns:
            BatchResult: Operation results

        Example:
            >>> operations = [
            ...     lambda: client.get_access_key("key1"),
            ...     lambda: client.delete_access_key("key2"),
            ...     lambda: client.rename_access_key("key3", "NewName"),
            ... ]
            >>> result = await batch.execute_custom_operations(operations)
        """

        async def execute_op(op: Callable[[], Awaitable[Any]]) -> Any:
            return await op()

        results = await self._processor.process(
            operations,
            execute_op,
            fail_fast=fail_fast,
        )

        return self._build_result(results)

    @staticmethod
    def _build_result(results: list[Any]) -> BatchResult:
        """Build BatchResult from results list."""
        successful = sum(1 for r in results if not isinstance(r, Exception))
        failed = len(results) - successful

        errors = [str(r) for r in results if isinstance(r, Exception)]

        return BatchResult(
            total=len(results),
            successful=successful,
            failed=failed,
            results=results,
            errors=errors,
        )


__all__ = [
    "BatchOperations",
    "BatchResult",
    "BatchProcessor",
]
