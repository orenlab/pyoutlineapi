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
from functools import cached_property
from typing import TYPE_CHECKING, Generic, TypeVar

from .common_types import Validators

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .client import AsyncOutlineClient
    from .models import AccessKey

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def _log_if_enabled(level: int, message: str) -> None:
    """Centralized logging with level check (DRY).

    :param level: Logging level
    :param message: Log message
    """
    if logger.isEnabledFor(level):
        logger.log(level, message)


@dataclass(slots=True, frozen=True)
class BatchResult(Generic[R]):
    """Result of batch operation with enhanced tracking.

    Immutable result object to prevent accidental modification.
    Uses cached_property for expensive computations.
    """

    total: int
    successful: int
    failed: int
    results: tuple[R | Exception, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    validation_errors: tuple[str, ...] = field(default_factory=tuple)

    @cached_property
    def success_rate(self) -> float:
        """Calculate success rate (cached).

        :return: Success rate as decimal (0.0 to 1.0)
        """
        if self.total == 0:
            return 1.0
        return self.successful / self.total

    @cached_property
    def has_errors(self) -> bool:
        """Check if any operations failed (cached).

        :return: True if any failures occurred
        """
        return self.failed > 0

    @cached_property
    def has_validation_errors(self) -> bool:
        """Check if any validation errors occurred (cached).

        :return: True if validation errors exist
        """
        return len(self.validation_errors) > 0

    def get_successful_results(self) -> list[R]:
        """Get only successful results (type-safe).

        :return: List of successful results
        """
        return [r for r in self.results if not isinstance(r, Exception)]

    def get_failures(self) -> list[Exception]:
        """Get only failures.

        :return: List of exceptions
        """
        return [r for r in self.results if isinstance(r, Exception)]

    @cached_property
    def _dict_cache(self) -> dict[str, object]:
        """Cached dictionary representation.

        :return: Dictionary representation
        """
        return {
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "has_errors": self.has_errors,
            "has_validation_errors": self.has_validation_errors,
            "validation_errors": list(self.validation_errors),
            "errors": list(self.errors),
        }

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for serialization (cached).

        :return: Dictionary representation
        """
        return self._dict_cache


class BatchProcessor(Generic[T, R]):
    """Generic batch processor with concurrency control and safety features."""

    __slots__ = ("_max_concurrent", "_semaphore", "_semaphore_lock")

    def __init__(self, max_concurrent: int = 5) -> None:
        """Initialize batch processor.

        :param max_concurrent: Maximum concurrent operations
        :raises ValueError: If max_concurrent is less than 1
        """
        if max_concurrent < 1:
            msg = "max_concurrent must be at least 1"
            raise ValueError(msg)

        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._semaphore_lock = asyncio.Lock()

    async def process(
        self,
        items: list[T],
        processor: Callable[[T], Awaitable[R]],
        *,
        fail_fast: bool = False,
    ) -> list[R | Exception]:
        """Process items in batch with concurrency control.

        :param items: Items to process
        :param processor: Async function to process each item
        :param fail_fast: Stop on first error
        :return: List of results or exceptions
        """
        if not items:
            return []

        async def process_single(item: T, index: int) -> R | Exception:
            async with self._semaphore:
                try:
                    result = await processor(item)
                    _log_if_enabled(
                        logging.DEBUG,
                        f"Batch item {index} completed successfully",
                    )
                    return result
                except Exception as e:
                    _log_if_enabled(
                        logging.DEBUG,
                        f"Batch item {index} failed: {e}",
                    )
                    if fail_fast:
                        raise
                    return e

        tasks = [process_single(item, i) for i, item in enumerate(items)]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=not fail_fast)

            return list(results) if isinstance(results, tuple) else results
        except Exception:
            for task in tasks:
                if isinstance(task, asyncio.Task) and not task.done():
                    task.cancel()
            raise

    async def set_concurrency(self, new_limit: int) -> None:
        """Change concurrency limit dynamically.

        :param new_limit: New concurrency limit
        :raises ValueError: If new_limit is less than 1
        """
        if new_limit < 1:
            msg = "Concurrency limit must be at least 1"
            raise ValueError(msg)

        async with self._semaphore_lock:
            if new_limit == self._max_concurrent:
                return

            self._max_concurrent = new_limit
            self._semaphore = asyncio.Semaphore(new_limit)

            _log_if_enabled(
                logging.DEBUG,
                f"Batch concurrency changed to {new_limit}",
            )


class ValidationHelper:
    """Helper class for batch validation logic (DRY)."""

    __slots__ = ()

    @staticmethod
    def validate_config_dict(
        config: object, index: int, fail_fast: bool
    ) -> dict[str, object] | None:
        """Validate and process config dictionary.

        :param config: Configuration to validate
        :param index: Config index for error reporting
        :param fail_fast: Whether to raise on error
        :return: Validated config or None if invalid
        :raises ValueError: If fail_fast and validation fails
        """
        if not isinstance(config, dict):
            error_msg = (
                f"Config {index}: must be a dictionary, got {type(config).__name__}"
            )
            if fail_fast:
                raise ValueError(error_msg)
            return None

        try:
            validated_config = config.copy()

            if config.get("name"):
                validated_name = Validators.validate_name(config["name"])
                if validated_name is None:
                    error_msg = f"Config {index}: name cannot be empty"
                    if fail_fast:
                        raise ValueError(error_msg)
                    return None
                validated_config["name"] = validated_name

            if "port" in config and config["port"] is not None:
                validated_config["port"] = Validators.validate_port(config["port"])

            return validated_config

        except ValueError as e:
            error_msg = f"Config {index}: {e}"
            if fail_fast:
                raise ValueError(error_msg) from e
            return None

    @staticmethod
    def validate_key_id(key_id: object, index: int, fail_fast: bool) -> str | None:
        """Validate key ID.

        :param key_id: Key ID to validate
        :param index: Key index for error reporting
        :param fail_fast: Whether to raise on error
        :return: Validated key ID or None if invalid
        :raises ValueError: If fail_fast and validation fails
        """
        if not isinstance(key_id, str):
            error_msg = f"Key {index}: must be a string, got {type(key_id).__name__}"
            if fail_fast:
                raise ValueError(error_msg)
            return None

        try:
            return Validators.validate_key_id(key_id)
        except ValueError as e:
            error_msg = f"Key {index} ({key_id}): {e}"
            if fail_fast:
                raise ValueError(error_msg) from e
            return None

    @staticmethod
    def validate_tuple_pair(
        pair: object, index: int, expected_types: tuple[type, ...], fail_fast: bool
    ) -> tuple[object, ...] | None:
        """Validate tuple pair.

        :param pair: Pair to validate
        :param index: Pair index for error reporting
        :param expected_types: Expected types for tuple elements
        :param fail_fast: Whether to raise on error
        :return: Validated pair or None if invalid
        :raises ValueError: If fail_fast and validation fails
        """
        if not isinstance(pair, tuple) or len(pair) != len(expected_types):
            error_msg = (
                f"Pair {index}: must be a {len(expected_types)}-tuple, "
                f"got {type(pair).__name__}"
            )
            if fail_fast:
                raise ValueError(error_msg)
            return None

        for i, (element, expected_type) in enumerate(
            zip(pair, expected_types, strict=False)
        ):
            if not isinstance(element, expected_type):
                error_msg = (
                    f"Pair {index}: element {i} must be {expected_type.__name__}, "
                    f"got {type(element).__name__}"
                )
                if fail_fast:
                    raise ValueError(error_msg)
                return None

        return pair


class BatchOperations:
    """Enhanced batch operations for AsyncOutlineClient with validation."""

    __slots__ = ("_client", "_max_concurrent", "_processor", "_validation_helper")

    def __init__(
        self,
        client: AsyncOutlineClient,
        *,
        max_concurrent: int = 5,
    ) -> None:
        """Initialize batch operations.

        :param client: AsyncOutlineClient instance
        :param max_concurrent: Maximum concurrent operations
        :raises ValueError: If max_concurrent is invalid
        """
        if max_concurrent < 1:
            msg = "max_concurrent must be at least 1"
            raise ValueError(msg)

        self._client = client
        self._max_concurrent = max_concurrent
        self._processor: BatchProcessor[dict[str, object], AccessKey] = BatchProcessor(
            max_concurrent
        )
        self._validation_helper = ValidationHelper()

    async def create_multiple_keys(
        self,
        configs: list[dict[str, object]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult[object] | BatchResult[AccessKey]:
        """Create multiple access keys in batch.

        :param configs: List of key configuration dictionaries
        :param fail_fast: Stop on first error
        :return: Batch operation result
        """
        if not configs:
            return self._build_empty_result()

        validation_errors: list[str] = []
        valid_configs: list[dict[str, object]] = []

        for i, config in enumerate(configs):
            validated = self._validation_helper.validate_config_dict(
                config, i, fail_fast
            )
            if validated is None:
                validation_errors.append(f"Config {i}: validation failed")
            else:
                valid_configs.append(validated)

        async def create_key(config: dict[str, object]) -> AccessKey:
            result = await self._client.create_access_key(**config)
            if TYPE_CHECKING:
                assert isinstance(result, AccessKey)
            return result

        processor: BatchProcessor[dict[str, object], AccessKey] = BatchProcessor(
            self._max_concurrent
        )
        results = await processor.process(
            valid_configs, create_key, fail_fast=fail_fast
        )

        return self._build_result(results, validation_errors)

    async def delete_multiple_keys(
        self,
        key_ids: list[str],
        *,
        fail_fast: bool = False,
    ) -> BatchResult[object] | BatchResult[bool]:
        """Delete multiple access keys in batch.

        :param key_ids: List of key IDs to delete
        :param fail_fast: Stop on first error
        :return: Batch operation result
        """
        if not key_ids:
            return self._build_empty_result()

        validated_ids: list[str] = []
        validation_errors: list[str] = []

        for i, key_id in enumerate(key_ids):
            validated = self._validation_helper.validate_key_id(key_id, i, fail_fast)
            if validated is None:
                validation_errors.append(f"Key {i}: validation failed")
            else:
                validated_ids.append(validated)

        async def delete_key(key_id: str) -> bool:
            return await self._client.delete_access_key(key_id)

        processor: BatchProcessor[str, bool] = BatchProcessor(self._max_concurrent)
        process_results = await processor.process(
            validated_ids, delete_key, fail_fast=fail_fast
        )

        return self._build_result(process_results, validation_errors)

    async def rename_multiple_keys(
        self,
        key_name_pairs: list[tuple[str, str]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult[object] | BatchResult[bool]:
        """Rename multiple access keys in batch.

        :param key_name_pairs: List of (key_id, new_name) tuples
        :param fail_fast: Stop on first error
        :return: Batch operation result
        """
        if not key_name_pairs:
            return self._build_empty_result()

        validated_pairs: list[tuple[str, str]] = []
        validation_errors: list[str] = []

        for i, pair in enumerate(key_name_pairs):
            validated = self._validation_helper.validate_tuple_pair(
                pair, i, (str, str), fail_fast
            )
            if validated is None:
                validation_errors.append(f"Pair {i}: validation failed")
                continue

            key_id, name = validated[0], validated[1]
            if not isinstance(key_id, str) or not isinstance(name, str):
                validation_errors.append(f"Pair {i}: invalid types")
                continue

            try:
                validated_id = Validators.validate_key_id(key_id)
                validated_name = Validators.validate_name(name)

                if validated_name is None:
                    error_msg = "Name cannot be empty"
                    if fail_fast:
                        raise ValueError(error_msg)
                    validation_errors.append(f"Pair {i}: name cannot be empty")
                    continue

                validated_pairs.append((validated_id, validated_name))

            except ValueError as e:
                error_msg = f"Pair {i}: {e}"
                if fail_fast:
                    raise ValueError(error_msg) from e
                validation_errors.append(error_msg)

        async def rename_key(pair: tuple[str, str]) -> bool:
            key_id, name = pair
            return await self._client.rename_access_key(key_id, name)

        processor: BatchProcessor[tuple[str, str], bool] = BatchProcessor(
            self._max_concurrent
        )
        results = await processor.process(
            validated_pairs, rename_key, fail_fast=fail_fast
        )

        return self._build_result(results, validation_errors)

    async def set_multiple_data_limits(
        self,
        key_limit_pairs: list[tuple[str, int]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult[object] | BatchResult[bool]:
        """Set data limits for multiple keys in batch.

        :param key_limit_pairs: List of (key_id, bytes_limit) tuples
        :param fail_fast: Stop on first error
        :return: Batch operation result
        """
        if not key_limit_pairs:
            return self._build_empty_result()

        validated_pairs: list[tuple[str, int]] = []
        validation_errors: list[str] = []

        for i, pair in enumerate(key_limit_pairs):
            validated = self._validation_helper.validate_tuple_pair(
                pair, i, (str, int), fail_fast
            )
            if validated is None:
                validation_errors.append(f"Pair {i}: validation failed")
                continue

            key_id, bytes_limit = validated[0], validated[1]
            if not isinstance(key_id, str) or not isinstance(bytes_limit, int):
                validation_errors.append(f"Pair {i}: invalid types")
                continue

            try:
                validated_id = Validators.validate_key_id(key_id)
                validated_bytes = Validators.validate_non_negative(
                    bytes_limit, "bytes_limit"
                )
                validated_pairs.append((validated_id, validated_bytes))

            except ValueError as e:
                error_msg = f"Pair {i}: {e}"
                if fail_fast:
                    raise ValueError(error_msg) from e
                validation_errors.append(error_msg)

        async def set_limit(pair: tuple[str, int]) -> bool:
            key_id, bytes_limit = pair
            return await self._client.set_access_key_data_limit(key_id, bytes_limit)

        processor: BatchProcessor[tuple[str, int], bool] = BatchProcessor(
            self._max_concurrent
        )
        results = await processor.process(
            validated_pairs, set_limit, fail_fast=fail_fast
        )

        return self._build_result(results, validation_errors)

    async def fetch_multiple_keys(
        self,
        key_ids: list[str],
        *,
        fail_fast: bool = False,
    ) -> BatchResult[object] | BatchResult[AccessKey]:
        """Fetch multiple access keys in batch.

        :param key_ids: List of key IDs to fetch
        :param fail_fast: Stop on first error
        :return: Batch operation result
        """
        if not key_ids:
            return self._build_empty_result()

        validated_ids: list[str] = []
        validation_errors: list[str] = []

        for i, key_id in enumerate(key_ids):
            validated = self._validation_helper.validate_key_id(key_id, i, fail_fast)
            if validated is None:
                validation_errors.append(f"Key {i}: validation failed")
            else:
                validated_ids.append(validated)

        async def fetch_key(key_id: str) -> AccessKey:
            result = await self._client.get_access_key(key_id)
            if TYPE_CHECKING:
                assert isinstance(result, AccessKey)
            return result

        processor: BatchProcessor[str, AccessKey] = BatchProcessor(self._max_concurrent)
        results = await processor.process(validated_ids, fetch_key, fail_fast=fail_fast)

        return self._build_result(results, validation_errors)

    async def execute_custom_operations(
        self,
        operations: list[Callable[[], Awaitable[object]]],
        *,
        fail_fast: bool = False,
    ) -> BatchResult[object]:
        """Execute custom batch operations.

        :param operations: List of async callables
        :param fail_fast: Stop on first error
        :return: Batch operation result
        """
        if not operations:
            return self._build_empty_result()

        validation_errors: list[str] = []
        valid_operations: list[Callable[[], Awaitable[object]]] = []

        for i, op in enumerate(operations):
            if not callable(op):
                error_msg = f"Operation {i}: must be callable, got {type(op).__name__}"
                if fail_fast:
                    raise ValueError(error_msg)
                validation_errors.append(error_msg)
                continue
            valid_operations.append(op)

        async def execute_op(op: Callable[[], Awaitable[object]]) -> object:
            return await op()

        processor: BatchProcessor[Callable[[], Awaitable[object]], object] = (
            BatchProcessor(self._max_concurrent)
        )
        results = await processor.process(
            valid_operations, execute_op, fail_fast=fail_fast
        )

        return self._build_result(results, validation_errors)

    async def set_concurrency(self, new_limit: int) -> None:
        """Change batch concurrency limit dynamically.

        :param new_limit: New concurrency limit
        :raises ValueError: If new_limit is invalid
        """
        await self._processor.set_concurrency(new_limit)
        self._max_concurrent = new_limit

    @staticmethod
    def _build_result(
        results: list[R | Exception],
        validation_errors: list[str],
    ) -> BatchResult[R]:
        """Build BatchResult from results list.

        :param results: List of results and exceptions
        :param validation_errors: List of validation error messages
        :return: Batch result object
        """
        successful = 0
        errors_list: list[str] = []

        for r in results:
            if isinstance(r, Exception):
                errors_list.append(str(r))
            else:
                successful += 1

        failed = len(results) - successful

        return BatchResult(
            total=len(results) + len(validation_errors),
            successful=successful,
            failed=failed + len(validation_errors),
            results=tuple(results),
            errors=tuple(errors_list),
            validation_errors=tuple(validation_errors),
        )

    @staticmethod
    def _build_empty_result() -> BatchResult[object]:
        """Build empty BatchResult for empty input.

        :return: Empty batch result
        """
        return BatchResult(
            total=0,
            successful=0,
            failed=0,
            results=(),
            errors=(),
            validation_errors=(),
        )


__all__ = [
    "BatchOperations",
    "BatchProcessor",
    "BatchResult",
]
