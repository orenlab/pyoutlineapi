from datetime import datetime, timezone
from typing import AsyncGenerator, Dict
from unittest.mock import MagicMock

import pytest
from aiohttp import ClientSession

from pyoutlineapi import AsyncOutlineClient, APIError
from pyoutlineapi.models import DataLimit

# Constants for testing
TEST_API_URL = "https://example.com:1234/secret"
TEST_CERT_SHA256 = "ab12cd34ef56gh78ij90kl12mn34op56qr78st90uvwxyzabcdef123456"
TEST_SERVER_ID = "server-id-123"
TEST_SERVER_NAME = "Test Server"


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
def server_info() -> Dict:
    """Base server information fixture."""
    return {
        "name": TEST_SERVER_NAME,
        "serverId": TEST_SERVER_ID,
        "metricsEnabled": True,
        "createdTimestampMs": int(datetime.now(timezone.utc).timestamp() * 1000),
        "version": "1.0.0",
        "portForNewAccessKeys": 8388,
        "hostnameForAccessKeys": "vpn.example.com",
        "accessKeyDataLimit": None,
    }


@pytest.fixture
def access_key_data() -> Dict:
    """Base access key data fixture."""
    return {
        "id": 1,
        "name": "Test Key",
        "password": "test-password",
        "port": 8388,
        "method": "chacha20-ietf-poly1305",
        "accessUrl": "ss://test-url",
        "dataLimit": None,
    }


@pytest.fixture
def access_key_list_data(access_key_data) -> Dict:
    """Access key list fixture."""
    return {"accessKeys": [access_key_data]}


@pytest.fixture
def metrics_data() -> Dict:
    """Server metrics fixture."""
    return {
        "bytesTransferredByUserId": {
            "1": 1024 * 1024 * 100,  # 100 MB
            "2": 1024 * 1024 * 200,  # 200 MB
        }
    }


@pytest.fixture
async def client() -> AsyncGenerator[AsyncOutlineClient, None]:
    """Fixture for AsyncOutlineClient with mocked session."""
    client = AsyncOutlineClient(TEST_API_URL, TEST_CERT_SHA256, json_format=True)

    # Create mock session
    mock_session = MagicMock(spec=ClientSession)
    mock_session.closed = False
    client._session = mock_session

    yield client

    # Cleanup
    if client.session and not client.session.closed:
        await client.session.close()


@pytest.fixture
def mock_successful_response():
    """Fixture for successful API responses."""

    def configure_response(data: dict):
        return MockResponse(status=200, data=data)

    return configure_response


@pytest.fixture
def mock_error_response():
    """Fixture for error API responses."""

    def configure_error(status_code: int, error_code: str, message: str):
        return MockResponse(
            status=status_code, data={"code": error_code, "message": message}
        )

    return configure_error


# Test case helpers
async def assert_request_called_with(
    client: AsyncOutlineClient,
    method: str,
    endpoint: str,
    json: dict = None,
    params: dict = None,
):
    """Helper to verify request parameters."""
    expected_url = f"{TEST_API_URL}/{endpoint.lstrip('/')}"
    client.session.request.assert_called_once_with(
        method, expected_url, json=json, params=params, raise_for_status=False
    )


@pytest.mark.asyncio
async def test_get_server_info(
    client: AsyncOutlineClient, server_info: Dict, mock_successful_response
):
    """Test get_server_info method."""
    # Configure mock response
    client._session.request.return_value = mock_successful_response(server_info)

    # Make request
    result = await client.get_server_info()

    # Verify request
    await assert_request_called_with(client, "GET", "server")

    # Verify response
    assert isinstance(result, dict)
    assert result["name"] == TEST_SERVER_NAME
    assert result["server_id"] == TEST_SERVER_ID


@pytest.mark.asyncio
async def test_create_access_key(
    client: AsyncOutlineClient, access_key_data: Dict, mock_successful_response
):
    """Test create_access_key method."""
    # Configure mock response
    client._session.request.return_value = mock_successful_response(access_key_data)

    # Test data
    key_name = "New Key"
    port = 8389
    data_limit = DataLimit(bytes=1024 * 1024 * 1024)  # 1 GB

    # Make request
    result = await client.create_access_key(name=key_name, port=port, limit=data_limit)

    # Verify request
    await assert_request_called_with(
        client,
        "POST",
        "access-keys",
        json={"name": key_name, "port": port, "limit": {"bytes": data_limit.bytes}},
    )

    # Verify response
    assert isinstance(result, dict)
    assert result["id"] == access_key_data["id"]


@pytest.mark.asyncio
async def test_get_metrics(
    client: AsyncOutlineClient, metrics_data: Dict, mock_successful_response
):
    """Test get_transfer_metrics method."""
    # Configure mock response
    client._session.request.return_value = mock_successful_response(metrics_data)

    # Make request
    result = await client.get_transfer_metrics()

    # Verify request
    await assert_request_called_with(
        client, "GET", "metrics/transfer", params={"period": "monthly"}
    )

    # Verify response
    assert isinstance(result, dict)
    assert "bytes_transferred_by_user_id" in result
    assert (
        result["bytes_transferred_by_user_id"]["1"]
        == metrics_data["bytesTransferredByUserId"]["1"]
    )


@pytest.mark.asyncio
async def test_error_handling(client: AsyncOutlineClient, mock_error_response):
    """Test API error handling."""
    # Configure error response
    error_code = "forbidden"
    error_message = "Access denied"
    client._session.request.return_value = mock_error_response(
        403, error_code, error_message
    )

    # Verify error is raised
    with pytest.raises(APIError) as exc_info:
        await client.get_server_info()

    assert exc_info.value.status_code == 403
    assert error_code in str(exc_info.value)
    assert error_message in str(exc_info.value)
