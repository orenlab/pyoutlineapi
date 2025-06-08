"""
Tests for PyOutlineAPI exceptions module.

PyOutlineAPI: A modern, async-first Python client for the Outline VPN Server API.

Copyright (c) 2025 Denis Rozhnovskiy <pytelemonbot@mail.ru>
All rights reserved.

This software is licensed under the MIT License.
You can find the full license text at:
    https://opensource.org/licenses/MIT

Source code repository:
    https://github.com/orenlab/pyoutlineapi
"""

import pytest
from pydantic import ValidationError

from pyoutlineapi import OutlineError, APIError
from pyoutlineapi.models import (
    AccessKey,
    AccessKeyCreateRequest,
    AccessKeyList,
    AccessKeyNameRequest,
    DataLimitRequest,
    ErrorResponse,
    ExperimentalMetrics,
    HostnameRequest,
    MetricsEnabledRequest,
    MetricsStatusResponse,
    PortRequest,
    Server,
    ServerMetrics,
    ServerNameRequest,
    DataLimit,
    TunnelTime,
    DataTransferred,
    BandwidthData,
    BandwidthInfo,
    LocationMetric,
    PeakDeviceCount,
    ConnectionInfo,
    AccessKeyMetric,
    ServerExperimentalMetric,
)


@pytest.fixture
def sample_access_key_data():
    """Sample access key data."""
    return {
        "id": "1",
        "name": "Test Key",
        "password": "test-password",
        "port": 8080,
        "method": "chacha20-ietf-poly1305",
        "accessUrl": "ss://test-url",
        "dataLimit": {"bytes": 1073741824}
    }


@pytest.fixture
def sample_access_key_list_data():
    """Sample access key list data."""
    return {
        "accessKeys": [
            {
                "id": "1",
                "password": "pass1",
                "port": 8080,
                "method": "aes-256-gcm",
                "accessUrl": "ss://url1"
            },
            {
                "id": "2",
                "password": "pass2",
                "port": 8081,
                "method": "chacha20-ietf-poly1305",
                "accessUrl": "ss://url2"
            }
        ]
    }


@pytest.fixture
def sample_server_data():
    """Sample server data."""
    return {
        "name": "Test Server",
        "serverId": "test-server-123",
        "metricsEnabled": True,
        "createdTimestampMs": 1640995200000,
        "version": "1.0.0",
        "portForNewAccessKeys": 8080,
        "hostnameForAccessKeys": "test.example.com",
        "accessKeyDataLimit": {"bytes": 1073741824}
    }


class TestDataLimit:
    """Test DataLimit model."""

    def test_valid_data_limit(self):
        """Test valid data limit creation."""
        limit = DataLimit(bytes=1024)
        assert limit.bytes == 1024

    def test_zero_bytes_allowed(self):
        """Test that zero bytes is allowed."""
        limit = DataLimit(bytes=0)
        assert limit.bytes == 0

    def test_negative_bytes_validation(self):
        """Test that negative bytes raises validation error."""
        with pytest.raises(ValidationError):
            DataLimit(bytes=-1)

    def test_large_bytes_value(self):
        """Test handling of large byte values."""
        large_value = 1024 * 1024 * 1024 * 1024  # 1TB
        limit = DataLimit(bytes=large_value)
        assert limit.bytes == large_value


class TestAccessKey:
    """Test AccessKey model."""

    def test_access_key_method_variations(self, sample_access_key_data):
        """Test different encryption methods."""
        methods = ["aes-256-gcm", "aes-192-gcm", "aes-128-gcm", "chacha20-ietf-poly1305"]

        for method in methods:
            sample_access_key_data["method"] = method
            key = AccessKey(**sample_access_key_data)
            assert key.method == method

    def test_access_key_with_minimal_data(self):
        """Test access key with only required fields."""
        minimal_data = {
            "id": "minimal",
            "password": "pass",
            "port": 8080,
            "method": "aes-256-gcm",
            "accessUrl": "ss://minimal-url"
        }
        key = AccessKey(**minimal_data)
        assert key.id == "minimal"
        assert key.name is None
        assert key.data_limit is None

    def test_valid_access_key(self, sample_access_key_data):
        """Test valid access key creation."""
        key = AccessKey(**sample_access_key_data)
        assert key.id == "1"
        assert key.name == "Test Key"
        assert key.password == "test-password"
        assert key.port == 8080
        assert key.method == "chacha20-ietf-poly1305"
        assert key.access_url == "ss://test-url"
        assert key.data_limit.bytes == 1073741824

    def test_access_key_without_name(self, sample_access_key_data):
        """Test access key creation without name."""
        del sample_access_key_data["name"]
        key = AccessKey(**sample_access_key_data)
        assert key.name is None

    def test_access_key_without_data_limit(self, sample_access_key_data):
        """Test access key creation without data limit."""
        del sample_access_key_data["dataLimit"]
        key = AccessKey(**sample_access_key_data)
        assert key.data_limit is None

    def test_invalid_port_validation(self, sample_access_key_data):
        """Test port validation."""
        sample_access_key_data["port"] = 0
        with pytest.raises(ValidationError):
            AccessKey(**sample_access_key_data)

        sample_access_key_data["port"] = 65536
        with pytest.raises(ValidationError):
            AccessKey(**sample_access_key_data)

    def test_valid_port_boundaries(self, sample_access_key_data):
        """Test valid port boundaries."""
        sample_access_key_data["port"] = 1
        key = AccessKey(**sample_access_key_data)
        assert key.port == 1

        sample_access_key_data["port"] = 65535
        key = AccessKey(**sample_access_key_data)
        assert key.port == 65535

    def test_field_aliases(self):
        """Test field aliases work correctly."""
        data = {
            "id": "1",
            "password": "pass",
            "port": 8080,
            "method": "aes-256-gcm",
            "accessUrl": "ss://url",  # Using alias
            "dataLimit": {"bytes": 1024},  # Using alias
        }
        key = AccessKey(**data)
        assert key.access_url == "ss://url"
        assert key.data_limit.bytes == 1024


class TestAccessKeyList:
    """Test AccessKeyList model."""

    def test_valid_access_key_list(self, sample_access_key_list_data):
        """Test valid access key list creation."""
        key_list = AccessKeyList(**sample_access_key_list_data)
        assert len(key_list.access_keys) == 2
        assert key_list.access_keys[0].id == "1"
        assert key_list.access_keys[1].id == "2"

    def test_empty_access_key_list(self):
        """Test empty access key list."""
        key_list = AccessKeyList(accessKeys=[])
        assert len(key_list.access_keys) == 0

    def test_field_alias(self):
        """Test field alias works correctly."""
        data = {"accessKeys": []}
        key_list = AccessKeyList(**data)
        assert isinstance(key_list.access_keys, list)


class TestServer:
    """Test Server model."""

    def test_server_metrics_enabled_false(self, sample_server_data):
        """Test server with metrics disabled."""
        sample_server_data["metricsEnabled"] = False
        server = Server(**sample_server_data)
        assert server.metrics_enabled is False

    def test_server_with_minimal_data(self):
        """Test server with only required fields."""
        minimal_data = {
            "name": "Minimal Server",
            "serverId": "minimal-123",
            "metricsEnabled": False,
            "createdTimestampMs": 1640995200000,
            "version": "1.0.0",
            "portForNewAccessKeys": 8080
        }
        server = Server(**minimal_data)
        assert server.hostname_for_access_keys is None
        assert server.access_key_data_limit is None

    def test_server_timestamp_boundaries(self, sample_server_data):
        """Test server with different timestamp values."""
        # Test with zero timestamp
        sample_server_data["createdTimestampMs"] = 0
        server = Server(**sample_server_data)
        assert server.created_timestamp_ms == 0

        # Test with large timestamp
        large_timestamp = 9999999999999
        sample_server_data["createdTimestampMs"] = large_timestamp
        server = Server(**sample_server_data)
        assert server.created_timestamp_ms == large_timestamp

    def test_valid_server(self, sample_server_data):
        """Test valid server creation."""
        server = Server(**sample_server_data)
        assert server.name == "Test Server"
        assert server.server_id == "test-server-123"
        assert server.metrics_enabled is True
        assert server.created_timestamp_ms == 1640995200000
        assert server.version == "1.0.0"
        assert server.port_for_new_access_keys == 8080
        assert server.hostname_for_access_keys == "test.example.com"
        assert server.access_key_data_limit.bytes == 1073741824

    def test_server_without_optional_fields(self, sample_server_data):
        """Test server without optional fields."""
        del sample_server_data["hostnameForAccessKeys"]
        del sample_server_data["accessKeyDataLimit"]

        server = Server(**sample_server_data)
        assert server.hostname_for_access_keys is None
        assert server.access_key_data_limit is None

    def test_invalid_port_validation(self, sample_server_data):
        """Test port validation for server."""
        sample_server_data["portForNewAccessKeys"] = 0
        with pytest.raises(ValidationError):
            Server(**sample_server_data)

        sample_server_data["portForNewAccessKeys"] = 65536
        with pytest.raises(ValidationError):
            Server(**sample_server_data)

    def test_valid_port_boundaries(self, sample_server_data):
        """Test valid port boundaries for server."""
        sample_server_data["portForNewAccessKeys"] = 1
        server = Server(**sample_server_data)
        assert server.port_for_new_access_keys == 1

        sample_server_data["portForNewAccessKeys"] = 65535
        server = Server(**sample_server_data)
        assert server.port_for_new_access_keys == 65535


class TestServerMetrics:
    """Test ServerMetrics model."""

    def test_server_metrics_with_string_keys(self):
        """Test ServerMetrics with various string key formats."""
        data = {
            "bytesTransferredByUserId": {
                "1": 1024,
                "key-with-dashes": 2048,
                "key_with_underscores": 512,
                "very-long-key-name-12345": 256
            }
        }
        metrics = ServerMetrics(**data)
        assert metrics.bytes_transferred_by_user_id["key-with-dashes"] == 2048
        assert metrics.bytes_transferred_by_user_id["key_with_underscores"] == 512

    def test_server_metrics_with_zero_values(self):
        """Test ServerMetrics with zero transfer values."""
        data = {"bytesTransferredByUserId": {"user1": 0, "user2": 0, "user3": 0}}
        metrics = ServerMetrics(**data)
        assert all(v == 0 for v in metrics.bytes_transferred_by_user_id.values())

    def test_valid_server_metrics(self):
        """Test valid server metrics creation."""
        data = {"bytesTransferredByUserId": {"1": 1024, "2": 2048, "3": 0}}
        metrics = ServerMetrics(**data)
        assert metrics.bytes_transferred_by_user_id["1"] == 1024
        assert metrics.bytes_transferred_by_user_id["2"] == 2048
        assert metrics.bytes_transferred_by_user_id["3"] == 0

    def test_empty_metrics(self):
        """Test empty server metrics."""
        data = {"bytesTransferredByUserId": {}}
        metrics = ServerMetrics(**data)
        assert len(metrics.bytes_transferred_by_user_id) == 0


class TestTunnelTime:
    """Test TunnelTime model."""

    def test_tunnel_time_negative_validation(self):
        """Test that negative seconds might be allowed (no explicit validation)."""
        # Check that model doesn't have explicit restrictions on negative values
        tunnel_time = TunnelTime(seconds=-100)
        assert tunnel_time.seconds == -100

    def test_valid_tunnel_time(self):
        """Test valid tunnel time creation."""
        tunnel_time = TunnelTime(seconds=3600)
        assert tunnel_time.seconds == 3600

    def test_zero_seconds(self):
        """Test zero seconds."""
        tunnel_time = TunnelTime(seconds=0)
        assert tunnel_time.seconds == 0


class TestDataTransferred:
    """Test DataTransferred model."""

    def test_data_transferred_negative_validation(self):
        """Test that negative bytes might be allowed (no explicit validation)."""
        # Check that model doesn't have explicit restrictions on negative values
        data_transferred = DataTransferred(bytes=-1024)
        assert data_transferred.bytes == -1024

    def test_data_transferred_large_value(self):
        """Test handling of very large byte values."""
        large_value = 2 ** 63 - 1  # Max int64
        data_transferred = DataTransferred(bytes=large_value)
        assert data_transferred.bytes == large_value

    def test_valid_data_transferred(self):
        """Test valid data transferred creation."""
        data_transferred = DataTransferred(bytes=1048576)
        assert data_transferred.bytes == 1048576

    def test_zero_bytes(self):
        """Test zero bytes."""
        data_transferred = DataTransferred(bytes=0)
        assert data_transferred.bytes == 0


class TestBandwidthData:
    """Test BandwidthData model."""

    def test_bandwidth_data_without_timestamp(self):
        """Test bandwidth data without timestamp."""
        bandwidth_data = BandwidthData(data={"bytes": 1024})
        assert bandwidth_data.data == {"bytes": 1024}
        assert bandwidth_data.timestamp is None

    def test_bandwidth_data_with_complex_data(self):
        """Test bandwidth data with complex data structure."""
        complex_data = {
            "bytes": 1024,
            "packets": 100,
            "errors": 0
        }
        bandwidth_data = BandwidthData(
            data=complex_data,
            timestamp=1640995200
        )
        assert bandwidth_data.data == complex_data
        assert bandwidth_data.timestamp == 1640995200

    def test_valid_bandwidth_data(self):
        """Test valid bandwidth data creation."""
        bandwidth_data = BandwidthData(
            data={"bytes": 1024},
            timestamp=1640995200
        )
        assert bandwidth_data.data == {"bytes": 1024}
        assert bandwidth_data.timestamp == 1640995200


class TestBandwidthInfo:
    """Test BandwidthInfo model."""

    def test_valid_bandwidth_info(self):
        """Test valid bandwidth info creation."""
        bandwidth_info = BandwidthInfo(
            current=BandwidthData(data={"bytes": 1024}, timestamp=1640995200),
            peak=BandwidthData(data={"bytes": 2048}, timestamp=1640995300)
        )
        assert bandwidth_info.current.data == {"bytes": 1024}
        assert bandwidth_info.peak.data == {"bytes": 2048}


class TestLocationMetric:
    """Test LocationMetric model."""

    def test_location_metric_with_valid_asn_and_org(self):
        """Test location metric with valid ASN and organization."""
        location_metric = LocationMetric(
            location="US",
            asn=12345,
            asOrg="Test Organization",
            tunnelTime=TunnelTime(seconds=1800),
            dataTransferred=DataTransferred(bytes=524288)
        )
        assert location_metric.asn == 12345
        assert location_metric.as_org == "Test Organization"

    def test_valid_location_metric(self):
        """Test valid location metric creation."""
        location_metric = LocationMetric(
            location="US",
            asn=12345,
            asOrg="Test AS",
            tunnelTime=TunnelTime(seconds=1800),
            dataTransferred=DataTransferred(bytes=524288)
        )
        assert location_metric.location == "US"
        assert location_metric.asn == 12345
        assert location_metric.as_org == "Test AS"
        assert location_metric.tunnel_time.seconds == 1800
        assert location_metric.data_transferred.bytes == 524288


class TestPeakDeviceCount:
    """Test PeakDeviceCount model."""

    def test_valid_peak_device_count(self):
        """Test valid peak device count creation."""
        peak_device_count = PeakDeviceCount(data=5, timestamp=1640995500)
        assert peak_device_count.data == 5
        assert peak_device_count.timestamp == 1640995500


class TestConnectionInfo:
    """Test ConnectionInfo model."""

    def test_connection_info_with_zero_timestamp(self):
        """Test connection info with zero timestamp."""
        connection_info = ConnectionInfo(
            lastTrafficSeen=0,
            peakDeviceCount=PeakDeviceCount(data=1, timestamp=0)
        )
        assert connection_info.last_traffic_seen == 0
        assert connection_info.peak_device_count.timestamp == 0

    def test_valid_connection_info(self):
        """Test valid connection info creation."""
        connection_info = ConnectionInfo(
            lastTrafficSeen=1640995400,
            peakDeviceCount=PeakDeviceCount(data=3, timestamp=1640995500)
        )
        assert connection_info.last_traffic_seen == 1640995400
        assert connection_info.peak_device_count.data == 3


class TestAccessKeyMetric:
    """Test AccessKeyMetric model."""

    def test_valid_access_key_metric(self):
        """Test valid access key metric creation."""
        access_key_metric = AccessKeyMetric(
            accessKeyId=1,
            tunnelTime=TunnelTime(seconds=900),
            dataTransferred=DataTransferred(bytes=262144),
            connection=ConnectionInfo(
                lastTrafficSeen=1640995400,
                peakDeviceCount=PeakDeviceCount(data=2, timestamp=1640995500)
            )
        )
        assert access_key_metric.access_key_id == 1
        assert access_key_metric.tunnel_time.seconds == 900
        assert access_key_metric.data_transferred.bytes == 262144
        assert access_key_metric.connection.last_traffic_seen == 1640995400


class TestServerExperimentalMetric:
    """Test ServerExperimentalMetric model."""

    def test_valid_server_experimental_metric(self):
        """Test valid server experimental metric creation."""
        server_metric = ServerExperimentalMetric(
            tunnelTime=TunnelTime(seconds=3600),
            dataTransferred=DataTransferred(bytes=1048576),
            bandwidth=BandwidthInfo(
                current=BandwidthData(data={"bytes": 1024}, timestamp=1640995200),
                peak=BandwidthData(data={"bytes": 2048}, timestamp=1640995300)
            ),
            locations=[
                LocationMetric(
                    location="US",
                    tunnelTime=TunnelTime(seconds=1800),
                    dataTransferred=DataTransferred(bytes=524288)
                )
            ]
        )
        assert server_metric.tunnel_time.seconds == 3600
        assert server_metric.data_transferred.bytes == 1048576
        assert len(server_metric.locations) == 1


class TestExperimentalMetrics:
    """Test ExperimentalMetrics model."""

    def test_experimental_metrics_field_aliases(self):
        """Test that field aliases work correctly."""
        data = {
            "server": {
                "tunnelTime": {"seconds": 100},
                "dataTransferred": {"bytes": 200},
                "bandwidth": {
                    "current": {"data": {"bytes": 10}, "timestamp": 1640995200},
                    "peak": {"data": {"bytes": 20}, "timestamp": 1640995300},
                },
                "locations": [],
            },
            "accessKeys": [],  # Using alias
        }

        metrics = ExperimentalMetrics(**data)
        assert isinstance(metrics.access_keys, list)
        assert len(metrics.access_keys) == 0

    def test_valid_experimental_metrics(self):
        """Test valid experimental metrics creation."""
        data = {
            "server": {
                "tunnelTime": {"seconds": 3600},
                "dataTransferred": {"bytes": 1048576},
                "bandwidth": {
                    "current": {"data": {"bytes": 1024}, "timestamp": 1640995200},
                    "peak": {"data": {"bytes": 2048}, "timestamp": 1640995300},
                },
                "locations": [
                    {
                        "location": "US",
                        "asn": 12345,
                        "asOrg": "Test AS",
                        "tunnelTime": {"seconds": 1800},
                        "dataTransferred": {"bytes": 524288},
                    }
                ],
            },
            "accessKeys": [
                {
                    "accessKeyId": 1,
                    "tunnelTime": {"seconds": 900},
                    "dataTransferred": {"bytes": 262144},
                    "connection": {
                        "lastTrafficSeen": 1640995400,
                        "peakDeviceCount": {"data": 5, "timestamp": 1640995500},
                    },
                }
            ],
        }

        metrics = ExperimentalMetrics(**data)
        assert metrics.server.tunnel_time.seconds == 3600
        assert metrics.server.data_transferred.bytes == 1048576
        assert len(metrics.access_keys) == 1
        assert metrics.access_keys[0].access_key_id == 1

    def test_experimental_metrics_with_empty_lists(self):
        """Test experimental metrics with empty access keys list."""
        data = {
            "server": {
                "tunnelTime": {"seconds": 0},
                "dataTransferred": {"bytes": 0},
                "bandwidth": {
                    "current": {"data": {"bytes": 0}, "timestamp": 1640995200},
                    "peak": {"data": {"bytes": 0}, "timestamp": 1640995300},
                },
                "locations": [],
            },
            "accessKeys": [],
        }

        metrics = ExperimentalMetrics(**data)
        assert len(metrics.server.locations) == 0
        assert len(metrics.access_keys) == 0


class TestRequestModels:
    """Test request models."""

    def test_access_key_create_request_with_method_variations(self):
        """Test AccessKeyCreateRequest with different methods."""
        methods = ["aes-256-gcm", "chacha20-ietf-poly1305", None]

        for method in methods:
            request = AccessKeyCreateRequest(method=method)
            assert request.method == method

    def test_server_name_request_with_special_characters(self):
        """Test ServerNameRequest with special characters."""
        special_names = [
            "Server-123",
            "Server_with_underscores",
            "Server in Russian",
            "Server with spaces",
            "Server@#$%"
        ]

        for name in special_names:
            request = ServerNameRequest(name=name)
            assert request.name == name

    def test_hostname_request_variations(self):
        """Test HostnameRequest with different hostname formats."""
        hostnames = [
            "example.com",
            "sub.example.com",
            "192.168.1.1",
            "localhost",
            "server-123.domain.org"
        ]

        for hostname in hostnames:
            request = HostnameRequest(hostname=hostname)
            assert request.hostname == hostname

    def test_access_key_name_request_empty_string(self):
        """Test AccessKeyNameRequest with empty string."""
        request = AccessKeyNameRequest(name="")
        assert request.name == ""

    def test_metrics_enabled_request_field_alias(self):
        """Test MetricsEnabledRequest field alias."""
        # Test using alias
        request = MetricsEnabledRequest(metricsEnabled=True)
        assert request.metrics_enabled is True

        # Test field access
        request = MetricsEnabledRequest(metricsEnabled=False)
        assert request.metrics_enabled is False

    def test_access_key_create_request_full(self):
        """Test AccessKeyCreateRequest model with all fields."""
        request = AccessKeyCreateRequest(
            name="Test",
            password="pass",
            port=8080,
            method="aes-256-gcm",
            limit=DataLimit(bytes=1024),
        )
        assert request.name == "Test"
        assert request.password == "pass"
        assert request.port == 8080
        assert request.method == "aes-256-gcm"
        assert request.limit.bytes == 1024

    def test_access_key_create_request_empty(self):
        """Test AccessKeyCreateRequest model with no fields."""
        request = AccessKeyCreateRequest()
        assert request.name is None
        assert request.password is None
        assert request.port is None
        assert request.method is None
        assert request.limit is None

    def test_access_key_create_request_invalid_port(self):
        """Test AccessKeyCreateRequest with invalid port."""
        with pytest.raises(ValidationError):
            AccessKeyCreateRequest(port=0)

        with pytest.raises(ValidationError):
            AccessKeyCreateRequest(port=65536)

    def test_server_name_request(self):
        """Test ServerNameRequest model."""
        request = ServerNameRequest(name="New Server Name")
        assert request.name == "New Server Name"

    def test_hostname_request(self):
        """Test HostnameRequest model."""
        request = HostnameRequest(hostname="new.example.com")
        assert request.hostname == "new.example.com"

    def test_port_request(self):
        """Test PortRequest model."""
        request = PortRequest(port=9090)
        assert request.port == 9090

        with pytest.raises(ValidationError):
            PortRequest(port=0)

        with pytest.raises(ValidationError):
            PortRequest(port=65536)

    def test_port_request_boundaries(self):
        """Test PortRequest boundaries."""
        request = PortRequest(port=1)
        assert request.port == 1

        request = PortRequest(port=65535)
        assert request.port == 65535

    def test_access_key_name_request(self):
        """Test AccessKeyNameRequest model."""
        request = AccessKeyNameRequest(name="New Key Name")
        assert request.name == "New Key Name"

    def test_data_limit_request(self):
        """Test DataLimitRequest model."""
        request = DataLimitRequest(limit=DataLimit(bytes=2048))
        assert request.limit.bytes == 2048

    def test_metrics_enabled_request(self):
        """Test MetricsEnabledRequest model."""
        request = MetricsEnabledRequest(metricsEnabled=True)
        assert request.metrics_enabled is True

        request = MetricsEnabledRequest(metricsEnabled=False)
        assert request.metrics_enabled is False


class TestResponseModels:
    """Test response models."""

    def test_metrics_status_response_field_alias(self):
        """Test MetricsStatusResponse field alias."""
        # Test using alias
        response = MetricsStatusResponse(metricsEnabled=True)
        assert response.metrics_enabled is True

    def test_error_response_with_empty_strings(self):
        """Test ErrorResponse with empty strings."""
        error = ErrorResponse(code="", message="")
        assert error.code == ""
        assert error.message == ""

    def test_error_response_with_long_messages(self):
        """Test ErrorResponse with long messages."""
        long_message = "A" * 1000  # Very long error message
        error = ErrorResponse(code="LONG_ERROR", message=long_message)
        assert error.code == "LONG_ERROR"
        assert error.message == long_message
        assert len(error.message) == 1000

    def test_metrics_status_response(self):
        """Test MetricsStatusResponse model."""
        response = MetricsStatusResponse(metricsEnabled=False)
        assert response.metrics_enabled is False

        response = MetricsStatusResponse(metricsEnabled=True)
        assert response.metrics_enabled is True

    def test_error_response(self):
        """Test ErrorResponse model."""
        error = ErrorResponse(code="NOT_FOUND", message="Resource not found")
        assert error.code == "NOT_FOUND"
        assert error.message == "Resource not found"

    def test_error_response_different_codes(self):
        """Test ErrorResponse with different error codes."""
        error = ErrorResponse(code="BAD_REQUEST", message="Invalid input")
        assert error.code == "BAD_REQUEST"
        assert error.message == "Invalid input"

        error = ErrorResponse(code="INTERNAL_ERROR", message="Server error")
        assert error.code == "INTERNAL_ERROR"
        assert error.message == "Server error"


class TestOutlineError:
    """Test OutlineError base exception."""

    def test_basic_outline_error(self):
        """Test basic OutlineError creation."""
        error = OutlineError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_outline_error_inheritance(self):
        """Test OutlineError inheritance."""
        error = OutlineError("Test")
        assert isinstance(error, Exception)

    def test_outline_error_no_message(self):
        """Test OutlineError without message."""
        error = OutlineError()
        assert isinstance(error, Exception)

    def test_outline_error_with_args(self):
        """Test OutlineError with multiple args."""
        error = OutlineError("Error", "Additional info")
        assert "Error" in str(error)


class TestAPIError:
    """Test APIError exception."""

    def test_basic_api_error(self):
        """Test basic APIError creation."""
        error = APIError("API failed")
        assert str(error) == "API failed"
        assert error.status_code is None
        assert error.attempt is None

    def test_api_error_with_status_code(self):
        """Test APIError with status code."""
        error = APIError("Not found", status_code=404)
        assert str(error) == "Not found"
        assert error.status_code == 404

    def test_api_error_with_attempt(self):
        """Test APIError with attempt number."""
        error = APIError("Timeout", attempt=2)
        assert str(error) == "[Attempt 2] Timeout"
        assert error.attempt == 2

    def test_api_error_with_all_params(self):
        """Test APIError with all parameters."""
        error = APIError("Server error", status_code=500, attempt=3)
        assert str(error) == "[Attempt 3] Server error"
        assert error.status_code == 500
        assert error.attempt == 3

    def test_api_error_inheritance(self):
        """Test APIError inheritance."""
        error = APIError("Test")
        assert isinstance(error, OutlineError)
        assert isinstance(error, Exception)

    def test_api_error_attempt_zero(self):
        """Test APIError with attempt 0."""
        error = APIError("Failed", attempt=0)
        assert str(error) == "[Attempt 0] Failed"
        assert error.attempt == 0

    def test_api_error_different_status_codes(self):
        """Test APIError with different status codes."""
        error_400 = APIError("Bad request", status_code=400)
        assert error_400.status_code == 400

        error_500 = APIError("Internal error", status_code=500)
        assert error_500.status_code == 500

        error_403 = APIError("Forbidden", status_code=403)
        assert error_403.status_code == 403
