"""
Tests for PyOutlineAPI client module.

PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

import logging
import time

import aiohttp
import pytest
from aioresponses import aioresponses

# Import the client and related classes
from pyoutlineapi.client import AsyncOutlineClient
from pyoutlineapi.exceptions import APIError
from pyoutlineapi.models import (
    AccessKey,
    AccessKeyList,
    DataLimit,
    MetricsStatusResponse,
    Server,
    ServerMetrics,
)


# Test data fixtures
@pytest.fixture
def valid_api_url():
    """Valid API URL for testing."""
    return "https://example.com:1234/secret"


@pytest.fixture
def valid_cert_sha256():
    """Valid SHA-256 certificate fingerprint."""
    return "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"


@pytest.fixture
def invalid_cert_sha256():
    """Invalid SHA-256 certificate fingerprint."""
    return "invalid_cert"


@pytest.fixture
def server_response():
    """Mock server information response."""
    return {
        "name": "Test Server",
        "serverId": "12345",
        "metricsEnabled": True,
        "createdTimestampMs": 1640995200000,
        "version": "1.0.0",
        "accessKeyDataLimit": {"bytes": 1073741824},
        "portForNewAccessKeys": 8388,
        "hostnameForAccessKeys": "example.com"
    }


@pytest.fixture
def access_key_response():
    """Mock access key response."""
    return {
        "id": "1",
        "name": "Test Key",
        "password": "test_password",
        "port": 8388,
        "method": "chacha20-ietf-poly1305",
        "accessUrl": "ss://test_url",
        "dataLimit": {"bytes": 1073741824}
    }


@pytest.fixture
def access_keys_list_response():
    """Mock access keys list response."""
    return {
        "accessKeys": [
            {
                "id": "1",
                "name": "Key 1",
                "password": "pass1",
                "port": 8388,
                "method": "chacha20-ietf-poly1305",
                "accessUrl": "ss://url1"
            },
            {
                "id": "2",
                "name": "Key 2",
                "password": "pass2",
                "port": 8389,
                "method": "chacha20-ietf-poly1305",
                "accessUrl": "ss://url2",
                "dataLimit": {"bytes": 2147483648}
            }
        ]
    }


@pytest.fixture
def metrics_status_response():
    """Mock metrics status response."""
    return {"metricsEnabled": True}


@pytest.fixture
def server_metrics_response():
    """Mock server metrics response."""
    return {
        "bytesTransferredByUserId": {
            "1": 1024000,
            "2": 2048000
        }
    }


@pytest.fixture
def experimental_metrics_response():
    """Mock experimental metrics response."""
    return {
        "server": {
            "tunnelTime": {"seconds": 3600},
            "dataTransferred": {"bytes": 1073741824}
        },
        "accessKeys": [
            {
                "id": "1",
                "tunnelTime": {"seconds": 1800},
                "dataTransferred": {"bytes": 536870912}
            }
        ]
    }


class TestAsyncOutlineClientInitialization:
    """Test client initialization and validation."""

    def test_valid_initialization(self, valid_api_url, valid_cert_sha256):
        """Test successful client initialization."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256)

        assert client._api_url == valid_api_url
        assert client._cert_sha256 == valid_cert_sha256
        assert client._json_format is False
        assert client._retry_attempts == 3
        assert client._enable_logging is False
        assert client._user_agent == "PyOutlineAPI/0.3.0"
        assert client._max_connections == 10
        assert client._rate_limit_delay == 0.0

    def test_initialization_with_custom_params(self, valid_api_url, valid_cert_sha256):
        """Test initialization with custom parameters."""
        client = AsyncOutlineClient(
            valid_api_url,
            valid_cert_sha256,
            json_format=True,
            timeout=60,
            retry_attempts=5,
            enable_logging=True,
            user_agent="Custom Agent",
            max_connections=20,
            rate_limit_delay=1.0
        )

        assert client._json_format is True
        assert client._timeout.total == 60
        assert client._retry_attempts == 5
        assert client._enable_logging is True
        assert client._user_agent == "Custom Agent"
        assert client._max_connections == 20
        assert client._rate_limit_delay == 1.0

    def test_empty_api_url_raises_error(self, valid_cert_sha256):
        """Test that empty API URL raises ValueError."""
        with pytest.raises(ValueError, match="api_url cannot be empty"):
            AsyncOutlineClient("", valid_cert_sha256)

    def test_whitespace_api_url_raises_error(self, valid_cert_sha256):
        """Test that whitespace-only API URL raises ValueError."""
        with pytest.raises(ValueError, match="api_url cannot be empty"):
            AsyncOutlineClient("   ", valid_cert_sha256)

    def test_empty_cert_sha256_raises_error(self, valid_api_url):
        """Test that empty certificate SHA256 raises ValueError."""
        with pytest.raises(ValueError, match="cert_sha256 cannot be empty"):
            AsyncOutlineClient(valid_api_url, "")

    def test_invalid_cert_sha256_format_raises_error(self, valid_api_url):
        """Test that invalid certificate format raises ValueError."""
        with pytest.raises(ValueError, match="cert_sha256 must contain only hexadecimal"):
            AsyncOutlineClient(valid_api_url, "invalid_hex_string")

    def test_wrong_cert_sha256_length_raises_error(self, valid_api_url):
        """Test that wrong certificate length raises ValueError."""
        with pytest.raises(ValueError, match="cert_sha256 must be exactly 64 hexadecimal"):
            AsyncOutlineClient(valid_api_url, "abcdef123456")

    def test_api_url_trailing_slash_removal(self, valid_cert_sha256):
        """Test that trailing slashes are removed from API URL."""
        client = AsyncOutlineClient("https://example.com/path/", valid_cert_sha256)
        assert client._api_url == "https://example.com/path"


class TestAsyncOutlineClientContextManager:
    """Test async context manager behavior."""

    @pytest.mark.asyncio
    async def test_context_manager_entry_exit(self, valid_api_url, valid_cert_sha256):
        """Test context manager entry and exit."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256)

        async with client as c:
            assert c is client
            assert client._session is not None
            assert not client._session.closed

        assert client._session is None

    @pytest.mark.asyncio
    async def test_create_factory_method(self, valid_api_url, valid_cert_sha256):
        """Test the create factory method."""
        async with AsyncOutlineClient.create(valid_api_url, valid_cert_sha256) as client:
            assert isinstance(client, AsyncOutlineClient)
            assert client._session is not None

    @pytest.mark.asyncio
    async def test_logging_setup_on_enter(self, valid_api_url, valid_cert_sha256, caplog):
        """Test logging setup when entering context manager."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256, enable_logging=True)

        with caplog.at_level(logging.INFO):
            async with client:
                pass

        assert "Initialized OutlineAPI client" in caplog.text
        assert "OutlineAPI client session closed" in caplog.text


class TestAsyncOutlineClientRequests:
    """Test HTTP request functionality."""

    @pytest.mark.asyncio
    async def test_ensure_context_decorator_without_session(self, valid_api_url, valid_cert_sha256):
        """Test that methods fail without active session."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256)

        with pytest.raises(RuntimeError, match="Client session is not initialized"):
            await client.get_server_info()

    @pytest.mark.asyncio
    async def test_build_url_with_valid_endpoint(self, valid_api_url, valid_cert_sha256):
        """Test URL building with valid endpoint."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256)

        url = client._build_url("server")
        assert url == f"{valid_api_url}/server"

        url = client._build_url("/server")
        assert url == f"{valid_api_url}/server"

    def test_build_url_with_invalid_endpoint(self, valid_api_url, valid_cert_sha256):
        """Test URL building with invalid endpoint."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256)

        with pytest.raises(ValueError, match="Endpoint must be a string"):
            client._build_url(None)

    def test_get_ssl_context_success(self, valid_api_url, valid_cert_sha256):
        """Test SSL context creation with valid certificate."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256)

        ssl_context = client._get_ssl_context()
        assert ssl_context is not None

    @pytest.mark.asyncio
    async def test_rate_limiting_applied(self, valid_api_url, valid_cert_sha256):
        """Test that rate limiting is applied correctly."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256, rate_limit_delay=0.1)

        start_time = time.time()
        await client._apply_rate_limiting()
        client._last_request_time = time.time()
        await client._apply_rate_limiting()
        end_time = time.time()

        # Should have delayed at least 0.1 seconds
        assert end_time - start_time >= 0.1

    @pytest.mark.asyncio
    async def test_rate_limiting_no_delay(self, valid_api_url, valid_cert_sha256):
        """Test that no rate limiting is applied when delay is 0."""
        client = AsyncOutlineClient(valid_api_url, valid_cert_sha256, rate_limit_delay=0.0)

        start_time = time.time()
        await client._apply_rate_limiting()
        await client._apply_rate_limiting()
        end_time = time.time()

        # Should not have significant delay
        assert end_time - start_time < 0.01


class TestAsyncOutlineClientRetryLogic:
    """Test retry logic functionality."""

    @pytest.mark.asyncio
    async def test_retry_success_on_second_attempt(self):
        """Test successful retry after initial failure."""
        call_count = 0

        async def failing_request():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise aiohttp.ClientError("Temporary failure")
            return "success"

        result = await AsyncOutlineClient._retry_request(failing_request, attempts=3)
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_attempts(self):
        """Test that retry stops after max attempts."""
        call_count = 0

        async def always_failing_request():
            nonlocal call_count
            call_count += 1
            raise aiohttp.ClientError("Always failing")

        with pytest.raises(APIError, match="Request failed after 2 attempts"):
            await AsyncOutlineClient._retry_request(always_failing_request, attempts=2)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_non_retriable_error(self):
        """Test that non-retriable errors are not retried."""
        call_count = 0

        async def non_retriable_error():
            nonlocal call_count
            call_count += 1
            raise APIError("Bad request", 400)

        with pytest.raises(APIError, match="Bad request"):
            await AsyncOutlineClient._retry_request(non_retriable_error, attempts=3)

        assert call_count == 1


class TestAsyncOutlineClientServerMethods:
    """Test server management methods."""

    @pytest.mark.asyncio
    async def test_get_server_info_success(self, valid_api_url, valid_cert_sha256, server_response):
        """Test successful server info retrieval."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/server", payload=server_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.get_server_info()

                assert isinstance(result, Server)
                assert result.name == "Test Server"
                assert result.server_id == "12345"

    @pytest.mark.asyncio
    async def test_get_server_info_json_format(self, valid_api_url, valid_cert_sha256, server_response):
        """Test server info retrieval in JSON format."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/server", payload=server_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256, json_format=True) as client:
                result = await client.get_server_info()

                assert isinstance(result, dict)
                assert result["name"] == "Test Server"

    @pytest.mark.asyncio
    async def test_rename_server_success(self, valid_api_url, valid_cert_sha256):
        """Test successful server renaming."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/name", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.rename_server("New Server Name")
                assert result is True

    @pytest.mark.asyncio
    async def test_set_hostname_success(self, valid_api_url, valid_cert_sha256):
        """Test successful hostname setting."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/server/hostname-for-access-keys", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.set_hostname("vpn.example.com")
                assert result is True

    @pytest.mark.asyncio
    async def test_set_default_port_success(self, valid_api_url, valid_cert_sha256):
        """Test successful default port setting."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/server/port-for-new-access-keys", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.set_default_port(8388)
                assert result is True

    @pytest.mark.asyncio
    async def test_set_default_port_invalid_range(self, valid_api_url, valid_cert_sha256):
        """Test port validation for invalid ranges."""
        async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
            with pytest.raises(ValueError, match="Privileged ports are not allowed"):
                await client.set_default_port(80)

            with pytest.raises(ValueError, match="Privileged ports are not allowed"):
                await client.set_default_port(70000)


class TestAsyncOutlineClientMetricsMethods:
    """Test metrics-related methods."""

    @pytest.mark.asyncio
    async def test_get_metrics_status_success(self, valid_api_url, valid_cert_sha256, metrics_status_response):
        """Test successful metrics status retrieval."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/metrics/enabled", payload=metrics_status_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.get_metrics_status()

                assert isinstance(result, MetricsStatusResponse)
                assert result.metrics_enabled is True

    @pytest.mark.asyncio
    async def test_set_metrics_status_success(self, valid_api_url, valid_cert_sha256):
        """Test successful metrics status setting."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/metrics/enabled", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.set_metrics_status(True)
                assert result is True

    @pytest.mark.asyncio
    async def test_get_transfer_metrics_success(self, valid_api_url, valid_cert_sha256, server_metrics_response):
        """Test successful transfer metrics retrieval."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/metrics/transfer", payload=server_metrics_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.get_transfer_metrics()

                assert isinstance(result, ServerMetrics)
                assert "1" in result.bytes_transferred_by_user_id


class TestAsyncOutlineClientAccessKeyMethods:
    """Test access key management methods."""

    @pytest.mark.asyncio
    async def test_create_access_key_success(self, valid_api_url, valid_cert_sha256, access_key_response):
        """Test successful access key creation."""
        with aioresponses() as m:
            m.post(f"{valid_api_url}/access-keys", payload=access_key_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.create_access_key(name="Test Key")

                assert isinstance(result, AccessKey)
                assert result.name == "Test Key"
                assert result.id == "1"

    @pytest.mark.asyncio
    async def test_create_access_key_with_all_params(self, valid_api_url, valid_cert_sha256, access_key_response):
        """Test access key creation with all parameters."""
        with aioresponses() as m:
            m.post(f"{valid_api_url}/access-keys", payload=access_key_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                limit = DataLimit(bytes=1024 ** 3)
                result = await client.create_access_key(
                    name="Full Key",
                    password="secret",
                    port=8388,
                    method="chacha20-ietf-poly1305",
                    limit=limit
                )

                assert isinstance(result, AccessKey)

    @pytest.mark.asyncio
    async def test_create_access_key_with_id(self, valid_api_url, valid_cert_sha256, access_key_response):
        """Test access key creation with specific ID."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/access-keys/custom-id", payload=access_key_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.create_access_key_with_id("custom-id", name="Custom Key")

                assert isinstance(result, AccessKey)

    @pytest.mark.asyncio
    async def test_get_access_keys_success(self, valid_api_url, valid_cert_sha256, access_keys_list_response):
        """Test successful access keys retrieval."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/access-keys", payload=access_keys_list_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.get_access_keys()

                assert isinstance(result, AccessKeyList)
                assert len(result.access_keys) == 2
                assert result.access_keys[0].id == "1"

    @pytest.mark.asyncio
    async def test_get_access_key_success(self, valid_api_url, valid_cert_sha256, access_key_response):
        """Test successful single access key retrieval."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/access-keys/1", payload=access_key_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.get_access_key("1")

                assert isinstance(result, AccessKey)
                assert result.id == "1"

    @pytest.mark.asyncio
    async def test_rename_access_key_success(self, valid_api_url, valid_cert_sha256):
        """Test successful access key renaming."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/access-keys/1/name", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.rename_access_key("1", "New Name")
                assert result is True

    @pytest.mark.asyncio
    async def test_delete_access_key_success(self, valid_api_url, valid_cert_sha256):
        """Test successful access key deletion."""
        with aioresponses() as m:
            m.delete(f"{valid_api_url}/access-keys/1", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.delete_access_key("1")
                assert result is True

    @pytest.mark.asyncio
    async def test_set_access_key_data_limit_success(self, valid_api_url, valid_cert_sha256):
        """Test successful access key data limit setting."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/access-keys/1/data-limit", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.set_access_key_data_limit("1", 1024 ** 3)
                assert result is True

    @pytest.mark.asyncio
    async def test_remove_access_key_data_limit_success(self, valid_api_url, valid_cert_sha256):
        """Test successful access key data limit removal."""
        with aioresponses() as m:
            m.delete(f"{valid_api_url}/access-keys/1/data-limit", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.remove_access_key_data_limit("1")
                assert result is True


class TestAsyncOutlineClientGlobalDataLimit:
    """Test global data limit methods."""

    @pytest.mark.asyncio
    async def test_set_global_data_limit_success(self, valid_api_url, valid_cert_sha256):
        """Test successful global data limit setting."""
        with aioresponses() as m:
            m.put(f"{valid_api_url}/server/access-key-data-limit", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.set_global_data_limit(100 * 1024 ** 3)
                assert result is True

    @pytest.mark.asyncio
    async def test_remove_global_data_limit_success(self, valid_api_url, valid_cert_sha256):
        """Test successful global data limit removal."""
        with aioresponses() as m:
            m.delete(f"{valid_api_url}/server/access-key-data-limit", status=204)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.remove_global_data_limit()
                assert result is True


class TestAsyncOutlineClientBatchOperations:
    """Test batch operations."""

    @pytest.mark.asyncio
    async def test_batch_create_access_keys_success(self, valid_api_url, valid_cert_sha256, access_key_response):
        """Test successful batch access key creation."""
        with aioresponses() as m:
            # Mock multiple POST requests
            for i in range(2):
                response_copy = access_key_response.copy()
                response_copy["id"] = str(i + 1)
                response_copy["name"] = f"Key {i + 1}"
                m.post(f"{valid_api_url}/access-keys", payload=response_copy)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                configs = [
                    {"name": "Key 1"},
                    {"name": "Key 2", "port": 8388}
                ]
                results = await client.batch_create_access_keys(configs)

                assert len(results) == 2
                assert all(isinstance(r, AccessKey) for r in results)

    @pytest.mark.asyncio
    async def test_batch_create_access_keys_with_failure(self, valid_api_url, valid_cert_sha256, access_key_response):
        """Test batch creation with some failures and fail_fast=False."""
        with aioresponses() as m:
            # First request succeeds
            m.post(f"{valid_api_url}/access-keys", payload=access_key_response)
            # Second request fails
            m.post(f"{valid_api_url}/access-keys", status=400, payload={"error": "Bad request"})

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                configs = [
                    {"name": "Key 1"},
                    {"name": "Key 2"}
                ]
                results = await client.batch_create_access_keys(configs, fail_fast=False)

                assert len(results) == 2
                assert isinstance(results[0], AccessKey)
                assert isinstance(results[1], Exception)

    @pytest.mark.asyncio
    async def test_batch_create_access_keys_fail_fast(self, valid_api_url, valid_cert_sha256):
        """Test batch creation with fail_fast=True."""
        with aioresponses() as m:
            m.post(f"{valid_api_url}/access-keys", status=400, payload={"error": "Bad request"})

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                configs = [{"name": "Key 1"}]

                with pytest.raises(APIError):
                    await client.batch_create_access_keys(configs, fail_fast=True)


class TestAsyncOutlineClientHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, valid_api_url, valid_cert_sha256, server_response):
        """Test successful health check."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/server", payload=server_response)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.health_check()
                assert result is True
                assert client.is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, valid_api_url, valid_cert_sha256):
        """Test health check failure."""
        with aioresponses() as m:
            m.get(f"{valid_api_url}/server", status=500)

            async with AsyncOutlineClient(valid_api_url, valid_cert_sha256) as client:
                result = await client.health_check()
                assert result is False
                assert client.is_healthy is False
