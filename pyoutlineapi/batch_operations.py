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
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .common_types import Validators

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .client import AsyncOutlineClient
    from .models import AccessKey

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass(slots=True)
class BatchResult:
    """Result of batch operation with enhanced tracking.

    IMPROVEMENTS:
    - Slots for memory efficiency
    - Better error categorization
    """

    total: int
    successful: int
    failed: int
    results: list[R | Exception] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total == 0:
            return 1.0
        return self.successful / self.total

    @property
    def has_errors(self) -> bool:
        """Check if any operations failed."""
        return self.failed > 0

    @property
    def has_validation_errors(self) -> bool:
        """Check if any validation errors occurred."""
        return len(self.validation_errors) > 0

    def get_successful_results(self) -> list[R]:
        """Get only successful results (type-safe)."""
        return [r for r in self.results if not isinstance(r, Exception)]

    def get_failures(self) -> list[Exception]:
        """Get only failures."""
        return [r for r in self.results if isinstance(r, Exception)]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "has_errors": self.has_errors,
            "has_validation_errors": self.has_validation_errors,
            "validation_errors": self.validation_errors,
            "errors": self.errors,
        }


class BatchProcessor(Generic[T, R]):
    """Generic batch processor with concurrency control.

    IMPROVEMENTS:
    - Better error handling
    - Type safety with generics
    - Strict typing for processor function
    """

    __slots__ = ("_max_concurrent", "_semaphore")

    def __init__(self, max_concurrent: int = 5) -> None:
        """Initialize batch processor."""
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")

        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def process(
        self,
        items: list[T],
        processor: Callable[[T], Awaitable[R]],
        *,
        fail_fast: bool = False,
    ) -> list[R | Exception]:
        """Process items in batch with concurrency control."""
        if not items:
            return []

        async def process_single(item: T) -> R | Exception:
            async with self._semaphore:
                try:
                    return await processor(item)
                except Exception as e:
                    if fail_fast:
                        raise
                    logger.debug(f"Batch item failed: {e}")
                    return e

        tasks = [process_single(item) for item in items]
        return await asyncio.gather(*tasks, return_exceptions=not fail_fast)


class BatchOperations:
    """Enhanced batch operations for AsyncOutlineClient.

    IMPROVEMENTS:
    - Better validation error tracking
    - Enhanced error messages
    - Type safety
    """

    __slots__ = ("_client", "_processor")

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        max_concurrent: int = 5,
    ) -> None:
        """Initialize batch operations."""
        self._client = client
        self._processor: BatchProcessor[Any, Any] = BatchProcessor(max_concurrent)

    async def create_multiple_keys(
        self,
        configs: list[dict[str, Any]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """Create multiple access keys in batch.

        IMPROVEMENTS:
        - Pre-validation of configs
        - Better error tracking
        """
        # Pre-validate configs
        validation_errors: list[str] = []
        valid_configs: list[dict[str, Any]] = []

        for i, config in enumerate(configs):
            try:
                # Validate name if present
                if config.get("name"):
                    validated_name = Validators.validate_name(config["name"])
                    if validated_name is None:
                        validation_errors.append(f"Config {i}: name cannot be empty")
                        continue

                # Validate port if present
                if config.get("port"):
                    Validators.validate_port(config["port"])

                valid_configs.append(config)

            except ValueError as e:
                validation_errors.append(f"Config {i}: {e}")
                if fail_fast:
                    raise

        # Process valid configs
        async def create_key(config: dict[str, Any]) -> AccessKey:
            return await self._client.create_access_key(**config)

        processor: BatchProcessor[dict[str, Any], AccessKey] = self._processor
        results = await processor.process(
            valid_configs, create_key, fail_fast=fail_fast
        )

        return self._build_result(results, validation_errors)

    async def delete_multiple_keys(
        self,
        key_ids: list[str],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """Delete multiple access keys in batch.

        IMPROVEMENTS:
        - Pre-validation of key_ids
        - Better error tracking
        """
        validated_ids: list[str] = []
        validation_errors: list[str] = []

        for i, key_id in enumerate(key_ids):
            try:
                validated_id = Validators.validate_key_id(key_id)
                validated_ids.append(validated_id)
            except ValueError as e:
                validation_errors.append(f"Key {i} ({key_id}): {e}")
                if fail_fast:
                    raise

        async def delete_key(key_id: str) -> bool:
            return await self._client.delete_access_key(key_id)

        processor: BatchProcessor[str, bool] = self._processor
        process_results = await processor.process(
            validated_ids, delete_key, fail_fast=fail_fast
        )

        return self._build_result(process_results, validation_errors)

    async def rename_multiple_keys(
        self,
        key_name_pairs: list[tuple[str, str]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """Rename multiple access keys in batch.

        IMPROVEMENTS:
        - Pre-validation of key_ids and names
        """
        validated_pairs: list[tuple[str, str]] = []
        validation_errors: list[str] = []

        for i, (key_id, name) in enumerate(key_name_pairs):
            try:
                validated_id = Validators.validate_key_id(key_id)
                validated_name = Validators.validate_name(name)

                if validated_name is None:
                    validation_errors.append(f"Pair {i}: name cannot be empty")
                    if fail_fast:
                        raise ValueError("Name cannot be empty")
                    continue

                validated_pairs.append((validated_id, validated_name))

            except ValueError as e:
                validation_errors.append(f"Pair {i}: {e}")
                if fail_fast:
                    raise

        async def rename_key(pair: tuple[str, str]) -> bool:
            key_id, name = pair
            return await self._client.rename_access_key(key_id, name)

        processor: BatchProcessor[tuple[str, str], bool] = self._processor
        results = await processor.process(
            validated_pairs, rename_key, fail_fast=fail_fast
        )

        return self._build_result(results, validation_errors)

    async def set_multiple_data_limits(
        self,
        key_limit_pairs: list[tuple[str, int]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """Set data limits for multiple keys in batch.

        IMPROVEMENTS:
        - Pre-validation of key_ids and limits
        """
        validated_pairs: list[tuple[str, int]] = []
        validation_errors: list[str] = []

        for i, (key_id, bytes_limit) in enumerate(key_limit_pairs):
            try:
                validated_id = Validators.validate_key_id(key_id)
                validated_bytes = Validators.validate_non_negative(
                    bytes_limit, "bytes_limit"
                )
                validated_pairs.append((validated_id, validated_bytes))

            except ValueError as e:
                validation_errors.append(f"Pair {i}: {e}")
                if fail_fast:
                    raise

        async def set_limit(pair: tuple[str, int]) -> bool:
            key_id, bytes_limit = pair
            return await self._client.set_access_key_data_limit(key_id, bytes_limit)

        processor: BatchProcessor[tuple[str, int], bool] = self._processor
        results = await processor.process(
            validated_pairs, set_limit, fail_fast=fail_fast
        )

        return self._build_result(results, validation_errors)

    async def fetch_multiple_keys(
        self,
        key_ids: list[str],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """Fetch multiple access keys in batch.

        IMPROVEMENTS:
        - Pre-validation of key_ids
        """
        validated_ids: list[str] = []
        validation_errors: list[str] = []

        for i, key_id in enumerate(key_ids):
            try:
                validated_id = Validators.validate_key_id(key_id)
                validated_ids.append(validated_id)
            except ValueError as e:
                validation_errors.append(f"Key {i} ({key_id}): {e}")
                if fail_fast:
                    raise

        async def fetch_key(key_id: str) -> AccessKey:
            return await self._client.get_access_key(key_id)

        processor: BatchProcessor[str, AccessKey] = self._processor
        results = await processor.process(validated_ids, fetch_key, fail_fast=fail_fast)

        return self._build_result(results, validation_errors)

    async def execute_custom_operations(
        self,
        operations: list[Callable[[], Awaitable[Any]]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult:
        """Execute custom batch operations."""

        async def execute_op(op: Callable[[], Awaitable[Any]]) -> Any:
            return await op()

        processor: BatchProcessor[Callable[[], Awaitable[Any]], Any] = self._processor
        results = await processor.process(operations, execute_op, fail_fast=fail_fast)

        return self._build_result(results, [])

    @staticmethod
    def _build_result(
        results: list[Any],
        validation_errors: list[str],
    ) -> BatchResult:
        """Build BatchResult from results list."""
        successful = sum(1 for r in results if not isinstance(r, Exception))
        failed = len(results) - successful

        errors = [str(r) for r in results if isinstance(r, Exception)]

        return BatchResult(
            total=len(results) + len(validation_errors),
            successful=successful,
            failed=failed + len(validation_errors),
            results=results,
            errors=errors,
            validation_errors=validation_errors,
        )


__all__ = [
    "BatchOperations",
    "BatchProcessor",
    "BatchResult",
]
