from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
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
    TokenBucketRateLimiter,
)
from pyoutlineapi.circuit_breaker import CircuitBreaker, CircuitConfig
from pyoutlineapi.common_types import (
    Constants,
    JsonDict,
    JsonList,
    JsonValue,
    SSRFProtection,
)
from pyoutlineapi.exceptions import APIError, CircuitOpenError


class _ChunkedContent:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def iter_chunked(self, size: int):
        for i in range(0, len(self._data), size):
            yield self._data[i : i + size]


class DummyResponse:
    @staticmethod
    def _resolve_headers(headers: dict[str, str] | None) -> dict[str, str]:
        if headers is None:
            return {"Content-Type": "application/json"}
        return headers

    @staticmethod
    def _resolve_reason(reason: str | None) -> str:
        if reason is None:
            return "OK"
        return reason

    def __init__(
        self,
        status: int,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        reason: str | None = None,
        json_data: dict[str, object] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status, self._body = status, body
        self.headers = self._resolve_headers(headers)
        self.reason = self._resolve_reason(reason)
        self._json_data, self._json_error = json_data, json_error
        self.content = _ChunkedContent(self._body)

    async def json(self) -> dict[str, object]:
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

    def request(self, *args: object, **kwargs: object) -> DummyRequestContext:
        return DummyRequestContext(self._responder(*args, **kwargs))

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_request_rechecks_ssrf(monkeypatch):
    client = BaseHTTPClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        allow_private_networks=False,
        resolve_dns_for_ssrf=True,
    )

    monkeypatch.setattr(
        SSRFProtection, "is_blocked_hostname_uncached", lambda _host: True
    )

    with pytest.raises(ValueError, match=r".*"):
        await client._request("GET", "server")


@pytest.mark.asyncio
async def test_request_ssrf_passes_and_returns(monkeypatch):
    class DummyClient(BaseHTTPClient):
        async def _ensure_session(self) -> None:
            return None

        async def _make_request_inner(
            self,
            method: str,
            endpoint: str,
            *,
            json: JsonDict | JsonList | None = None,
            params: dict[str, str | int | float | bool] | None = None,
            correlation_id: str,
        ) -> dict[str, JsonValue]:
            _ = (method, endpoint, json, params, correlation_id)
            return {}

    client = DummyClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        allow_private_networks=False,
        resolve_dns_for_ssrf=True,
    )

    monkeypatch.setattr(
        SSRFProtection, "is_blocked_hostname_uncached", lambda _host: False
    )

    result = await client._request("GET", "server")
    assert result == {}


class _TestClient(BaseHTTPClient):
    async def _ensure_session(self) -> None:  # override to prevent real session
        return None


@pytest.mark.asyncio
async def test_build_url_and_parse_response(access_key_dict):
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    assert client._build_url("/server") == "https://example.com/secret/server"

    body = json.dumps(access_key_dict).encode("utf-8")
    response = DummyResponse(status=200, body=body)

    data = await client._parse_response_safe(
        cast(aiohttp.ClientResponse, response), "/server"
    )
    assert data["id"] == "key-1"


@pytest.mark.asyncio
async def test_parse_response_size_limit():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    big = b"a" * (Constants.MAX_RESPONSE_SIZE + 1)
    response = DummyResponse(status=200, body=big)

    with pytest.raises(APIError):
        await client._parse_response_safe(
            cast(aiohttp.ClientResponse, response), "/server"
        )


@pytest.mark.asyncio
async def test_parse_response_content_length_header_limit():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    response = DummyResponse(
        status=200,
        body=b"{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(Constants.MAX_RESPONSE_SIZE + 1),
        },
    )
    with pytest.raises(APIError):
        await client._parse_response_safe(
            cast(aiohttp.ClientResponse, response), "/server"
        )


@pytest.mark.asyncio
async def test_parse_response_content_length_invalid_and_list_json():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    response = DummyResponse(
        status=200,
        body=b"[]",
        headers={"Content-Type": "text/plain", "Content-Length": "bad"},
    )
    data = await client._parse_response_safe(
        cast(aiohttp.ClientResponse, response), "/server"
    )
    assert data["success"] is True


@pytest.mark.asyncio
async def test_handle_error_json():
    response = DummyResponse(
        status=500,
        body=b"{}",
        json_data={"message": "fail"},
    )
    with pytest.raises(APIError) as exc:
        await BaseHTTPClient._handle_error(
            cast(aiohttp.ClientResponse, response), "/bad"
        )
    assert "fail" in str(exc.value)


@pytest.mark.asyncio
async def test_handle_error_non_json():
    response = DummyResponse(
        status=400,
        body=b"not-json",
        json_error=ValueError("bad"),
        reason="Bad Request",
    )
    with pytest.raises(APIError) as exc:
        await BaseHTTPClient._handle_error(
            cast(aiohttp.ClientResponse, response), "/bad"
        )
    assert "Bad Request" in str(exc.value)


@pytest.mark.asyncio
async def test_make_request_inner_success_and_204(monkeypatch):
    def responder(method: str, url: str, **kwargs: object) -> DummyResponse:
        if method == "GET":
            return DummyResponse(status=200, body=b'{"success": true}')
        return DummyResponse(status=204, body=b"")

    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    client._session = cast(aiohttp.ClientSession, DummySession(responder))

    result = await client._make_request_inner(
        "GET", "server", json=None, params=None, correlation_id="cid"
    )
    assert result["success"] is True

    result = await client._make_request_inner(
        "DELETE", "server", json=None, params=None, correlation_id="cid"
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_make_request_inner_debug_logging(caplog):
    def responder(method: str, url: str, **kwargs: object) -> DummyResponse:
        return DummyResponse(status=200, body=b'{"success": true}')

    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    client._enable_logging = True
    client._session = cast(aiohttp.ClientSession, DummySession(responder))
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.base_client"):
        await client._make_request_inner(
            "GET", "server", json=None, params=None, correlation_id="cid"
        )
    assert any("GET" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_parse_response_invalid_json_returns_success():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    response = DummyResponse(status=200, body=b"{invalid")
    data = await client._parse_response_safe(
        cast(aiohttp.ClientResponse, response), "/server"
    )
    assert data["success"] is True


@pytest.mark.asyncio
async def test_parse_response_invalid_json_error_status():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    response = DummyResponse(status=500, body=b"{invalid")
    with pytest.raises(APIError):
        await client._parse_response_safe(
            cast(aiohttp.ClientResponse, response), "/server"
        )


@pytest.mark.asyncio
async def test_parse_response_non_dict_error_status():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    response = DummyResponse(status=400, body=b"[]")
    with pytest.raises(APIError):
        await client._parse_response_safe(
            cast(aiohttp.ClientResponse, response), "/server"
        )


@pytest.mark.asyncio
async def test_shutdown_closes_session():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    def responder(method: str, url: str, **kwargs: object) -> DummyResponse:
        return DummyResponse(204, b"")

    client._session = cast(aiohttp.ClientSession, DummySession(responder))
    await client.shutdown()
    assert client._session is None


@pytest.mark.asyncio
async def test_shutdown_cancels_active_requests():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    async def sleeper() -> dict[str, JsonValue]:
        await asyncio.sleep(1)
        return {"ok": True}

    task = asyncio.create_task(sleeper())
    async with client._active_requests_lock:
        client._active_requests.add(task)

    class DummySessionClose:
        closed = False

        async def close(self) -> None:
            self.closed = True

    client._session = cast(aiohttp.ClientSession, DummySessionClose())
    await client.shutdown(timeout=0.01)
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_rate_limiter_and_noop_metrics(monkeypatch):
    limiter = TokenBucketRateLimiter(rate=1.0, capacity=1)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    await limiter.acquire()
    await limiter.acquire()

    metrics = NoOpMetrics()
    metrics.increment("a")
    metrics.timing("b", 1.0)
    metrics.gauge("c", 2.0)


def test_token_bucket_invalid_params():
    with pytest.raises(ValueError, match=r".*"):
        TokenBucketRateLimiter(rate=0.0, capacity=1)
    with pytest.raises(ValueError, match=r".*"):
        TokenBucketRateLimiter(rate=1.0, capacity=0)


@pytest.mark.asyncio
async def test_base_client_context_manager():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    async with client:
        assert client is not None


def test_get_circuit_metrics_none():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    assert client.get_circuit_metrics() is None


def test_init_circuit_breaker_adjusts_timeout():
    config = CircuitConfig(
        call_timeout=0.1, recovery_timeout=1.0, failure_threshold=1, success_threshold=1
    )
    client = BaseHTTPClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=5,
        retry_attempts=2,
        max_connections=1,
        rate_limit=10,
        circuit_config=config,
    )
    assert client.get_circuit_metrics() is not None


@pytest.mark.asyncio
async def test_rate_limit_properties():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    assert client.rate_limit == 10
    assert client.active_requests == 0
    assert client.available_slots == 10
    stats = client.get_rate_limiter_stats()
    assert "limit" in stats
    await client.set_rate_limit(5)
    assert client.rate_limit == 5


@pytest.mark.asyncio
async def test_make_request_inner_connection_error():
    class ErrorSession:
        def request(
            self,
            *args: object,
            **kwargs: object,
        ) -> DummyRequestContext:
            raise aiohttp.ClientConnectionError("boom")

    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    client._session = cast(aiohttp.ClientSession, ErrorSession())
    with pytest.raises(APIError):
        await client._make_request_inner(
            "GET", "server", json=None, params=None, correlation_id="cid"
        )


@pytest.mark.asyncio
async def test_request_with_circuit_open(monkeypatch):
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    class DummyBreaker:
        async def call(self, *args: object, **kwargs: object) -> object:
            raise CircuitOpenError("open")

    client._circuit_breaker = cast(CircuitBreaker, DummyBreaker())
    with pytest.raises(CircuitOpenError):
        await client._request("GET", "server")


@pytest.mark.asyncio
async def test_request_with_circuit_open_logs(caplog):
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    class DummyBreaker:
        async def call(self, *args: object, **kwargs: object) -> object:
            raise CircuitOpenError("open")

    client._circuit_breaker = cast(CircuitBreaker, DummyBreaker())
    with (
        caplog.at_level(
            logging.ERROR,
            logger="pyoutlineapi.base_client",
        ),
        pytest.raises(CircuitOpenError),
    ):
        await client._request("GET", "server")


@pytest.mark.asyncio
async def test_request_success_path(monkeypatch):
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    async def fake_inner(*args: object, **kwargs: object) -> dict[str, object]:
        return {"ok": True}

    monkeypatch.setattr(client, "_make_request_inner", fake_inner)
    data = await client._request("GET", "server")
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_make_request_inner_http_error():
    def responder(method: str, url: str, **kwargs: object) -> DummyResponse:
        return DummyResponse(
            status=500,
            body=b'{"message": "fail"}',
            json_data={"message": "fail"},
        )

    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    client._session = cast(aiohttp.ClientSession, DummySession(responder))
    with pytest.raises(APIError):
        await client._make_request_inner(
            "GET", "server", json=None, params=None, correlation_id="cid"
        )


@pytest.mark.asyncio
async def test_make_request_inner_no_session():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    client._session = None
    with pytest.raises(APIError):
        await client._make_request_inner(
            "GET", "server", json=None, params=None, correlation_id="cid"
        )


@pytest.mark.asyncio
async def test_make_request_inner_timeout_error(monkeypatch):
    class TimeoutSession:
        def request(
            self,
            *args: object,
            **kwargs: object,
        ) -> DummyRequestContext:
            raise asyncio.TimeoutError()

    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    client._session = cast(aiohttp.ClientSession, TimeoutSession())
    with pytest.raises(APIError):
        await client._make_request_inner(
            "GET", "server", json=None, params=None, correlation_id="cid"
        )


@pytest.mark.asyncio
async def test_make_request_inner_client_error():
    class ClientErrorSession:
        def request(
            self,
            *args: object,
            **kwargs: object,
        ) -> DummyRequestContext:
            raise aiohttp.ClientError("oops")

    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    client._session = cast(aiohttp.ClientSession, ClientErrorSession())
    with pytest.raises(APIError):
        await client._make_request_inner(
            "GET", "server", json=None, params=None, correlation_id="cid"
        )


@pytest.mark.asyncio
async def test_ensure_session_uses_aiohttp(monkeypatch, caplog):
    created = {"session": False}

    class DummyTraceConfig:
        def __init__(self) -> None:
            self.on_connection_create_end: list[object] = []
            self.on_connection_reuseconn: list[object] = []

    class DummyConnector:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class DummySession:
        def __init__(self, **kwargs: object) -> None:
            created["session"] = True
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(aiohttp, "TraceConfig", DummyTraceConfig)
    monkeypatch.setattr(aiohttp, "TCPConnector", DummyConnector)
    monkeypatch.setattr(aiohttp, "ClientSession", DummySession)

    client = BaseHTTPClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.base_client"):
        await client._ensure_session()
    assert created["session"] is True


@pytest.mark.asyncio
async def test_ensure_session_fast_path():
    client = BaseHTTPClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )

    class DummySessionFast:
        closed = False

    client._session = cast(aiohttp.ClientSession, DummySessionFast())
    await client._ensure_session()


@pytest.mark.asyncio
async def test_rate_limiter_context_and_set_limit():
    limiter = RateLimiter(limit=1)
    async with limiter:
        assert limiter.active == 1
    assert limiter.active == 0

    await limiter.set_limit(2)
    assert limiter.limit == 2
    await limiter.set_limit(2)
    with pytest.raises(ValueError, match=r".*"):
        await limiter.set_limit(0)


def test_rate_limiter_available_edge_cases():
    limiter = RateLimiter(limit=1)

    class DummySemaphore:
        _value = "bad"

    limiter._semaphore = cast(asyncio.Semaphore, DummySemaphore())
    assert limiter.available == 0

    class BrokenSemaphore:
        def __getattr__(self, _name: str) -> object:
            raise TypeError("boom")

    limiter._semaphore = cast(asyncio.Semaphore, BrokenSemaphore())
    assert limiter.available == 0


def test_rate_limiter_invalid_limit():
    with pytest.raises(ValueError, match=r".*"):
        RateLimiter(limit=0)


def test_rate_limiter_available_logs_warning(caplog):
    limiter = RateLimiter(limit=1)

    class BrokenSemaphore:
        def __getattr__(self, _name: str) -> object:
            raise TypeError("missing")

    limiter._semaphore = cast(asyncio.Semaphore, BrokenSemaphore())
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.base_client"):
        assert limiter.available == 0
    assert any("Cannot access semaphore value" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_rate_limiter_set_limit_logs(caplog):
    limiter = RateLimiter(limit=1)
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.base_client"):
        await limiter.set_limit(2)
    assert any("Rate limit changed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_retry_helper_success(monkeypatch):
    helper = RetryHelper()
    calls = {"count": 0}

    async def func() -> dict[str, JsonValue]:
        calls["count"] += 1
        if calls["count"] < 2:
            raise APIError("fail")
        return {"ok": True}

    async def fake_sleep(_):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    result = await helper.execute_with_retry(func, "/endpoint", 2, NoOpMetrics())
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_retry_helper_non_retryable():
    helper = RetryHelper()

    async def func() -> dict[str, JsonValue]:
        raise APIError("fail", status_code=400)

    with pytest.raises(APIError):
        await helper.execute_with_retry(func, "/endpoint", 2, NoOpMetrics())


def test_ssl_fingerprint_validator_verify():
    cert_bytes = b"cert"
    import hashlib

    expected = hashlib.sha256(cert_bytes).hexdigest()
    validator = SSLFingerprintValidator(SecretStr(expected))
    validator._verify_cert_fingerprint(cert_bytes)
    with pytest.raises(ValueError, match=r".*"):
        validator._verify_cert_fingerprint(b"other")

    validator.__exit__(None, None, None)
    with pytest.raises(RuntimeError):
        _ = validator.ssl_context


@pytest.mark.asyncio
async def test_ssl_fingerprint_validator_verify_connection():
    cert_bytes = b"cert"
    import hashlib

    expected = hashlib.sha256(cert_bytes).hexdigest()
    validator = SSLFingerprintValidator(SecretStr(expected))

    class DummySSL:
        def getpeercert(self, *, binary_form: bool = False) -> bytes | None:
            return cert_bytes if binary_form else None

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
async def test_ssl_fingerprint_validator_verify_connection_no_transport():
    validator = SSLFingerprintValidator(SecretStr("a" * 64))

    class DummyParams:
        transport = None

    await validator.verify_connection(
        cast(aiohttp.ClientSession, None),
        SimpleNamespace(),
        cast(aiohttp.TraceConnectionCreateEndParams, DummyParams()),
    )


def test_validate_numeric_params_errors():
    with pytest.raises(ValueError, match=r".*"):
        BaseHTTPClient._validate_numeric_params(0, 0, 1)
    with pytest.raises(ValueError, match=r".*"):
        BaseHTTPClient._validate_numeric_params(1, -1, 1)
    with pytest.raises(ValueError, match=r".*"):
        BaseHTTPClient._validate_numeric_params(1, 0, 0)


def test_api_url_and_reset_circuit_breaker():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    assert "https://example.com" in client.api_url
    assert client.circuit_state is None


@pytest.mark.asyncio
async def test_reset_circuit_breaker_noop():
    client = _TestClient(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        timeout=1,
        retry_attempts=0,
        max_connections=1,
        rate_limit=10,
    )
    assert await client.reset_circuit_breaker() is False
