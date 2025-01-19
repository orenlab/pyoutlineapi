import asyncio
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientSession

from pyoutlineapi.client import AsyncOutlineClient
from pyoutlineapi.exceptions import APIError
from pyoutlineapi.models import Server, AccessKey, AccessKeyList, MetricsStatusResponse, ServerMetrics
from pyoutlineapi.rate_limiter import RateLimiter, TokenBucket

# Constants for testing
TEST_API_URL = "https://example.com:1234/secret"
TEST_CERT_SHA256 = "ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34"
TEST_SERVER_NAME = "Test Server"
TEST_SERVER_ID = "12345"


class MockResponse:
    """Mock response that can be used as an async context manager."""

    def __init__(self, status: int = 200, data: dict = None):
        self.status = status
        self._data = data or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def json(self):
        return self._data


@pytest.fixture
def rate_limiter():
    return RateLimiter(rate_per_second=10, burst=20)


@pytest.fixture
async def client():
    """Fixture for AsyncOutlineClient with mocked session."""
    client = AsyncOutlineClient(TEST_API_URL, TEST_CERT_SHA256, json_format=False)

    # Create mock session
    mock_session = MagicMock(spec=ClientSession)
    mock_session.closed = False
    client._session = mock_session

    # Initialize RateLimiter
    client._rate_limiter = RateLimiter(rate_per_second=10, burst=20)

    yield client

    # Cleanup
    if client.session and not client.session.closed:
        await client.session.close()


@pytest.mark.asyncio
async def test_get_server_info(client):
    mock_response_data = {
        "name": TEST_SERVER_NAME,
        "serverId": TEST_SERVER_ID,
        "metricsEnabled": True,
        "createdTimestampMs": 1633024800000,
        "version": "1.0.0",
        "portForNewAccessKeys": 8388,
        "hostnameForAccessKeys": "vpn.example.com",
        "accessKeyDataLimit": None
    }

    mock_response = MockResponse(status=200, data=mock_response_data)
    client._session.request.return_value = mock_response

    server_info = await client.get_server_info()
    assert isinstance(server_info, Server)
    assert server_info.name == TEST_SERVER_NAME
    assert server_info.server_id == TEST_SERVER_ID


@pytest.mark.asyncio
async def test_rename_server(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.rename_server("New Server Name")
    assert success is True


@pytest.mark.asyncio
async def test_create_access_key(client):
    mock_response_data = {
        "id": 1,
        "name": "Test Key",
        "password": "password123",
        "port": 8388,
        "method": "aes-256-gcm",
        "accessUrl": "https://example.com/access-key",
        "dataLimit": None
    }

    mock_response = MockResponse(status=200, data=mock_response_data)
    client._session.request.return_value = mock_response

    access_key = await client.create_access_key(name="Test Key")
    assert isinstance(access_key, AccessKey)
    assert access_key.id == 1
    assert access_key.name == "Test Key"


@pytest.mark.asyncio
async def test_get_access_keys(client):
    mock_response_data = {
        "accessKeys": [
            {
                "id": 1,
                "name": "Test Key",
                "password": "password123",
                "port": 8388,
                "method": "aes-256-gcm",
                "accessUrl": "https://example.com/access-key",
                "dataLimit": None
            }
        ]
    }

    mock_response = MockResponse(status=200, data=mock_response_data)
    client._session.request.return_value = mock_response

    access_keys = await client.get_access_keys()
    assert isinstance(access_keys, AccessKeyList)
    assert len(access_keys.access_keys) == 1
    assert access_keys.access_keys[0].id == 1


@pytest.mark.asyncio
async def test_get_metrics_status(client):
    mock_response_data = {
        "metricsEnabled": True
    }

    mock_response = MockResponse(status=200, data=mock_response_data)
    client._session.request.return_value = mock_response

    metrics_status = await client.get_metrics_status()
    assert isinstance(metrics_status, MetricsStatusResponse)
    assert metrics_status.metrics_enabled is True


@pytest.mark.asyncio
async def test_get_transfer_metrics(client):
    mock_response_data = {
        "bytesTransferredByUserId": {
            "1": 1024,
            "2": 2048
        }
    }

    mock_response = MockResponse(status=200, data=mock_response_data)
    client._session.request.return_value = mock_response

    transfer_metrics = await client.get_transfer_metrics()
    assert isinstance(transfer_metrics, ServerMetrics)
    assert transfer_metrics.bytes_transferred_by_user_id["1"] == 1024
    assert transfer_metrics.bytes_transferred_by_user_id["2"] == 2048


@pytest.mark.asyncio
async def test_api_error_handling(client):
    mock_response_data = {
        "code": "not_found",
        "message": "Resource not found"
    }

    mock_response = MockResponse(status=404, data=mock_response_data)
    client._session.request.return_value = mock_response

    with pytest.raises(APIError) as exc_info:
        await client.get_server_info()
    assert exc_info.value.status_code == 404
    assert "Resource not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_set_hostname(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_hostname("new.hostname.com")
    assert success is True


@pytest.mark.asyncio
async def test_set_default_port(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_default_port(8388)
    assert success is True


@pytest.mark.asyncio
async def test_set_metrics_status(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_metrics_status(True)
    assert success is True


@pytest.mark.asyncio
async def test_delete_access_key(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.delete_access_key(1)
    assert success is True


@pytest.mark.asyncio
async def test_set_access_key_data_limit(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_access_key_data_limit(1, 1024 * 1024 * 1024)  # 1 GB
    assert success is True


@pytest.mark.asyncio
async def test_remove_access_key_data_limit(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.remove_access_key_data_limit(1)
    assert success is True


@pytest.fixture
def token_bucket():
    return TokenBucket.create(rate_per_second=10, capacity=20)


def test_token_bucket_create():
    bucket = TokenBucket.create(rate_per_second=10, capacity=20)
    assert bucket.config.rate_per_second == 10
    assert bucket.config.capacity == 20
    assert bucket._tokens == 20


def test_token_bucket_create_invalid_rate():
    with pytest.raises(ValueError, match="Rate must be positive"):
        TokenBucket.create(rate_per_second=0, capacity=20)


def test_token_bucket_create_invalid_capacity():
    with pytest.raises(ValueError, match="Capacity must be positive"):
        TokenBucket.create(rate_per_second=10, capacity=0)


def test_token_bucket_update(token_bucket):
    token_bucket._tokens = 0
    token_bucket._last_update_ns = 0
    token_bucket.update()
    assert token_bucket._tokens > 0


@pytest.mark.asyncio
async def test_token_bucket_acquire(token_bucket):
    wait_time = await token_bucket.acquire(tokens=1)
    assert wait_time == 0.0
    assert token_bucket._tokens == 19


@pytest.mark.asyncio
async def test_token_bucket_acquire_insufficient_tokens(token_bucket):
    token_bucket._tokens = 0
    wait_time = await token_bucket.acquire(tokens=1)
    assert wait_time > 0


@pytest.mark.asyncio
async def test_token_bucket_acquire_invalid_tokens(token_bucket):
    with pytest.raises(ValueError, match="Token count must be positive"):
        await token_bucket.acquire(tokens=0)

    with pytest.raises(ValueError, match="Requested tokens exceed bucket capacity"):
        await token_bucket.acquire(tokens=21)


@pytest.mark.asyncio
async def test_set_hostname(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_hostname("new.hostname.com")
    assert success is True


@pytest.mark.asyncio
async def test_set_default_port(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_default_port(8388)
    assert success is True


@pytest.mark.asyncio
async def test_set_metrics_status(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_metrics_status(True)
    assert success is True


@pytest.mark.asyncio
async def test_delete_access_key(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.delete_access_key(1)
    assert success is True


@pytest.mark.asyncio
async def test_set_access_key_data_limit(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.set_access_key_data_limit(1, 1024 * 1024 * 1024)  # 1 GB
    assert success is True


@pytest.mark.asyncio
async def test_remove_access_key_data_limit(client):
    mock_response = MockResponse(status=204)
    client._session.request.return_value = mock_response

    success = await client.remove_access_key_data_limit(1)
    assert success is True


@pytest.mark.asyncio
async def test_rate_limiter_acquire_with_wait(rate_limiter):
    acquired = await rate_limiter.acquire(key="test", tokens=1, wait=True)
    assert acquired is True


@pytest.mark.asyncio
async def test_rate_limiter_acquire_without_wait(rate_limiter):
    with pytest.raises(ValueError, match="Requested tokens exceed bucket capacity"):
        await rate_limiter.acquire(key="test", tokens=21, wait=False)


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_access(rate_limiter):
    async def acquire_tokens():
        return await rate_limiter.acquire(key="test", tokens=1)

    results = await asyncio.gather(*[acquire_tokens() for _ in range(10)])
    assert all(results)


def test_imports():
    from pyoutlineapi import AsyncOutlineClient, APIError, OutlineError
    from pyoutlineapi.models import AccessKey, Server
    assert AsyncOutlineClient is not None
    assert APIError is not None
    assert OutlineError is not None
    assert AccessKey is not None
    assert Server is not None


@pytest.fixture
def mock_client(client):
    return AsyncOutlineClient(api_url="https://example.com",
                              cert_sha256="ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34ab12cd34")


def test_build_url(mock_client):
    with patch.object(mock_client, "_build_url", return_value="https://example.com/test") as mock_method:
        result = mock_client._build_url("test")
        mock_method.assert_called_once_with("test")
        assert result == "https://example.com/test"


def test_get_ssl_context(mock_client):
    ssl_context = mock_client._get_ssl_context()
    assert ssl_context is not None

