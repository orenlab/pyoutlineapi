from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest


class DummyAuditLogger:
    def __init__(self) -> None:
        self.logged: list[tuple[str, str, dict[str, Any] | None, str | None]] = []
        self.alogged: list[tuple[str, str, dict[str, Any] | None, str | None]] = []

    def log_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.logged.append((action, resource, details, correlation_id))

    async def alog_action(
        self,
        action: str,
        resource: str,
        *,
        user: str | None = None,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.alogged.append((action, resource, details, correlation_id))


class DummyMetrics:
    def __init__(self) -> None:
        self.counters: list[tuple[str, dict[str, str] | None]] = []
        self.timings: list[tuple[str, float, dict[str, str] | None]] = []

    def increment(self, name: str, tags: dict[str, str] | None = None) -> None:
        self.counters.append((name, tags))

    def timing(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        self.timings.append((name, value, tags))


class _ChunkedContent:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def iter_chunked(self, size: int):
        for i in range(0, len(self._data), size):
            yield self._data[i : i + size]


class DummyResponse:
    def __init__(
        self,
        status: int,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        reason: str | None = None,
        json_data: dict[str, Any] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self.reason = reason or "OK"
        self._body = body
        self._json_data = json_data
        self._json_error = json_error
        self.content = _ChunkedContent(body)

    async def json(self) -> dict[str, Any]:
        if self._json_error is not None:
            raise self._json_error
        if self._json_data is not None:
            return self._json_data
        return {}


class DummyRequestContext:
    def __init__(self, response: DummyResponse) -> None:
        self._response = response

    async def __aenter__(self) -> DummyResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class DummySession:
    def __init__(self, responder: Callable[..., DummyResponse]) -> None:
        self._responder = responder
        self.closed = False

    def request(self, *args: Any, **kwargs: Any) -> DummyRequestContext:
        return DummyRequestContext(self._responder(*args, **kwargs))

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def access_key_dict() -> dict[str, Any]:
    return {
        "id": "key-1",
        "name": "Alice",
        "password": "secret",
        "port": 12345,
        "method": "aes-256-gcm",
        "accessUrl": "ss://example",
        "dataLimit": {"bytes": 1024},
    }


@pytest.fixture
def server_dict() -> dict[str, Any]:
    return {
        "name": "My Server",
        "serverId": "srv-1",
        "metricsEnabled": True,
        "createdTimestampMs": 1000,
        "portForNewAccessKeys": 23456,
        "hostnameForAccessKeys": "example.com",
        "accessKeyDataLimit": {"bytes": 2048},
        "version": "1.0.0",
    }


@pytest.fixture
def access_keys_list(access_key_dict: dict[str, Any]) -> dict[str, Any]:
    return {"accessKeys": [access_key_dict]}


@pytest.fixture
def server_metrics_dict() -> dict[str, Any]:
    return {"bytesTransferredByUserId": {"user-1": 100, "user-2": 200}}


@pytest.fixture
def experimental_metrics_dict() -> dict[str, Any]:
    return {
        "server": {
            "tunnelTime": {"seconds": 10},
            "dataTransferred": {"bytes": 1234},
            "bandwidth": {
                "current": {"data": {"bytes": 1}, "timestamp": 1},
                "peak": {"data": {"bytes": 2}, "timestamp": 2},
            },
            "locations": [],
        },
        "accessKeys": [
            {
                "accessKeyId": "key-1",
                "tunnelTime": {"seconds": 5},
                "dataTransferred": {"bytes": 100},
                "connection": {
                    "lastTrafficSeen": 1,
                    "peakDeviceCount": {"data": 1, "timestamp": 1},
                },
            }
        ],
    }


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    return asyncio.get_event_loop_policy()
