from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import cast

import aiohttp
import pytest
from pydantic import SecretStr

from pyoutlineapi.base_client import (
    BaseHTTPClient,
    NoOpMetrics,
    RateLimiter,
    RetryHelper,
    SSLFingerprintValidator,
)
from pyoutlineapi.circuit_breaker import CircuitBreaker
from pyoutlineapi.common_types import JsonValue
from pyoutlineapi.exceptions import APIError, CircuitOpenError


class DummyResponse:
    def __init__(self, status: int, reason: str = "Bad") -> None:
        self.status = status
        self.reason = reason

    async def json(self) -> dict[str, object]:
        raise TypeError("bad")


class _ChunkedContent:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def iter_chunked(self, size: int):
        for i in range(0, len(self._data), size):
            yield self._data[i : i + size]


class SimpleResponse:
    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self.reason = "OK"
        self.headers = {"Content-Type": "application/json"}
        self._body = body
        self.content = _ChunkedContent(body)

    async def json(self) -> dict[str, object]:
        return {}


class _TestClient(BaseHTTPClient):
    async def _ensure_session(self) -> None:  # override to prevent real session
        return None


class DummySession:
    def __init__(self, response: object) -> None:
        self._response = response
        self.closed = False

    def request(self, *args: object, **kwargs: object) -> object:
        return self._response

    async def close(self) -> None:
        self.closed = True


def test_rate_limiter_available_attribute_error(caplog):
    limiter = RateLimiter(limit=1)
    logging.getLogger("pyoutlineapi.base_client").setLevel(logging.WARNING)

    class BrokenSemaphore:
        def __getattribute__(self, _name: str) -> object:
            raise AttributeError("missing")

    limiter._semaphore = cast(asyncio.Semaphore, BrokenSemaphore())
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.base_client"):
        assert limiter.available == 0


def test_ssl_fingerprint_validator_expected_secret_missing():
    validator = SSLFingerprintValidator(SecretStr("a" * 64))
    validator.__exit__(None, None, None)
    with pytest.raises(RuntimeError):
        validator._verify_cert_fingerprint(b"cert")


@pytest.mark.asyncio
async def test_ssl_fingerprint_validator_verify_connection_no_ssl_object():
    validator = SSLFingerprintValidator(SecretStr("a" * 64))

    class DummyTransport:
        def get_extra_info(self, name: str) -> object:
            return None

    class DummyParams:
        transport = DummyTransport()

    await validator.verify_connection(
        cast(aiohttp.ClientSession, None),
        SimpleNamespace(),
        cast(aiohttp.TraceConnectionCreateEndParams, DummyParams()),
    )


@pytest.mark.asyncio
async def test_ssl_fingerprint_validator_verify_connection_empty_cert():
    validator = SSLFingerprintValidator(SecretStr("a" * 64))

    class DummySSL:
        def getpeercert(self, *, binary_form: bool = False) -> bytes | None:
            return b""

    class DummyTransport:
        def get_extra_info(self, name: str) -> object:
            if name == "ssl_object":
                return DummySSL()
            return None

    class DummyParams:
        transport = DummyTransport()

    await validator.verify_connection(
        cast(aiohttp.ClientSession, None),
        SimpleNamespace(),
        cast(aiohttp.TraceConnectionCreateEndParams, DummyParams()),
    )


@pytest.mark.asyncio
async def test_handle_error_type_error():
    with pytest.raises(APIError):
        await BaseHTTPClient._handle_error(
            cast(aiohttp.ClientResponse, DummyResponse(500)),
            "/bad",
        )


@pytest.mark.asyncio
async def test_shutdown_already_in_progress():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=1,
    )
    client._shutdown_event.set()
    await client.shutdown()


@pytest.mark.asyncio
async def test_shutdown_logs_and_cancels(caplog):
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=1,
    )

    async def sleeper() -> dict[str, JsonValue]:
        await asyncio.sleep(1)
        return {"ok": True}

    task = asyncio.create_task(sleeper())
    async with client._active_requests_lock:
        client._active_requests.add(task)

    class DummySession:
        closed = False

        async def close(self) -> None:
            self.closed = True

    client._session = cast(aiohttp.ClientSession, DummySession())

    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.base_client"):
        await client.shutdown(timeout=0.01)
    assert any("Shutdown timeout" in r.message for r in caplog.records)
    assert any("HTTP client shutdown complete" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_request_circuit_open_logs_error(caplog):
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=1,
    )

    class DummyBreaker:
        async def call(self, *args: object, **kwargs: object) -> object:
            raise CircuitOpenError("open")

    client._circuit_breaker = cast(CircuitBreaker, DummyBreaker())
    logging.getLogger("pyoutlineapi.base_client").setLevel(logging.ERROR)
    with caplog.at_level(
        logging.ERROR,
        logger="pyoutlineapi.base_client",
    ), pytest.raises(CircuitOpenError):
        await client._request("GET", "server")


@pytest.mark.asyncio
async def test_retry_helper_logs_warning(caplog):
    helper = RetryHelper()
    logging.getLogger("pyoutlineapi.base_client").setLevel(logging.WARNING)

    async def boom() -> dict[str, JsonValue]:
        raise APIError("fail", status_code=500)

    with caplog.at_level(
        logging.WARNING,
        logger="pyoutlineapi.base_client",
    ), pytest.raises(APIError):
        await helper.execute_with_retry(boom, "/endpoint", 0, NoOpMetrics())
    assert any("Request to" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_retry_helper_no_warning_when_logger_disabled():
    helper = RetryHelper()
    logging.getLogger("pyoutlineapi.base_client").setLevel(logging.ERROR)

    async def boom() -> dict[str, JsonValue]:
        raise APIError("fail", status_code=500)

    with pytest.raises(APIError):
        await helper.execute_with_retry(boom, "/endpoint", 0, NoOpMetrics())


@pytest.mark.asyncio
async def test_ensure_session_double_check_returns(monkeypatch):
    client = BaseHTTPClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=1,
    )

    class DummySessionFast:
        closed = False

    class DummyLock:
        async def __aenter__(self) -> None:
            client._session = cast(aiohttp.ClientSession, DummySessionFast())

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object | None,
        ) -> None:
            return None

    client._session = None
    client._session_lock = cast(asyncio.Lock, DummyLock())
    await client._ensure_session()
    assert client._session is not None


@pytest.mark.asyncio
async def test_active_requests_tracking():
    entered = asyncio.Event()
    continue_event = asyncio.Event()

    class DummyContext:
        async def __aenter__(self) -> SimpleResponse:
            entered.set()
            await continue_event.wait()
            return SimpleResponse()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object | None,
        ) -> None:
            return None

    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=1,
    )
    client._session = cast(aiohttp.ClientSession, DummySession(DummyContext()))

    task = asyncio.create_task(
        client._make_request_inner(
            "GET", "server", json=None, params=None, correlation_id="cid"
        )
    )
    await entered.wait()
    assert client.active_requests == 1
    continue_event.set()
    await task
    assert client.active_requests == 0


@pytest.mark.asyncio
async def test_reset_circuit_breaker_configured():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=1,
    )

    class DummyBreaker:
        async def reset(self) -> None:
            return None

        @property
        def metrics(self) -> object:
            return None

    client._circuit_breaker = cast(CircuitBreaker, DummyBreaker())
    assert await client.reset_circuit_breaker() is True
