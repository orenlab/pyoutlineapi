import pytest
from pydantic import ValidationError

from pyoutlineapi.models import Server, AccessKey, DataLimit, MetricsStatusResponse, ServerMetrics, AccessKeyList, \
    ExperimentalMetrics


def test_server_model():
    server_data = {
        "name": "Test Server",
        "serverId": "12345",
        "metricsEnabled": True,
        "createdTimestampMs": 1633024800000,
        "version": "1.0.0",
        "portForNewAccessKeys": 8388,
        "hostnameForAccessKeys": "vpn.example.com",
        "accessKeyDataLimit": None
    }

    server = Server(**server_data)
    assert server.name == "Test Server"
    assert server.server_id == "12345"
    assert server.metrics_enabled is True


def test_access_key_model():
    access_key_data = {
        "id": 1,
        "name": "Test Key",
        "password": "password123",
        "port": 8388,
        "method": "aes-256-gcm",
        "accessUrl": "https://example.com/access-key",
        "dataLimit": None
    }

    access_key = AccessKey(**access_key_data)
    assert access_key.id == 1
    assert access_key.name == "Test Key"
    assert access_key.port == 8388


def test_data_limit_validation():
    data_limit = DataLimit(bytes=1024)
    assert data_limit.bytes == 1024

    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        DataLimit(bytes=-500)

    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        DataLimit(bytes=0)


def test_metrics_status_response_model():
    metrics_status = MetricsStatusResponse(metricsEnabled=True)
    assert metrics_status.metrics_enabled is True


def test_server_metrics_model():
    server_metrics_data = {
        "bytesTransferredByUserId": {
            "1": 1024,
            "2": 2048
        }
    }

    server_metrics = ServerMetrics(**server_metrics_data)
    assert server_metrics.bytes_transferred_by_user_id["1"] == 1024
    assert server_metrics.bytes_transferred_by_user_id["2"] == 2048


def test_access_key_list_model():
    access_key_list_data = {
        "accessKeys": [
            {
                "id": 1,
                "name": "Key 1",
                "password": "pass1",
                "port": 8388,
                "method": "aes-256-gcm",
                "accessUrl": "https://example.com/key1",
                "dataLimit": {"bytes": 1024}
            },
            {
                "id": 2,
                "name": "Key 2",
                "password": "pass2",
                "port": 8389,
                "method": "chacha20-ietf-poly1305",
                "accessUrl": "https://example.com/key2",
                "dataLimit": None
            }
        ]
    }

    access_key_list = AccessKeyList(**access_key_list_data)
    assert len(access_key_list.access_keys) == 2
    assert access_key_list.access_keys[0].id == 1
    assert access_key_list.access_keys[0].data_limit.bytes == 1024
    assert access_key_list.access_keys[1].data_limit is None


def test_experimental_metrics_model():
    metrics_data = {
        "server": [
            {
                "location": "US",
                "asn": 12345,
                "asOrg": "Example ISP",
                "tunnelTime": {"seconds": 3600},
                "dataTransferred": {"bytes": 1048576}
            }
        ],
        "accessKeys": [
            {
                "accessKeyId": 1,
                "tunnelTime": {"seconds": 7200},
                "dataTransferred": {"bytes": 2097152}
            }
        ]
    }

    metrics = ExperimentalMetrics(**metrics_data)
    assert len(metrics.server) == 1
    assert metrics.server[0].asn == 12345
    assert metrics.server[0].data_transferred.bytes == 1048576
    assert len(metrics.access_keys) == 1
    assert metrics.access_keys[0].access_key_id == 1


def test_data_limit_validator():
    data_limit = DataLimit(bytes=2048)
    assert data_limit.bytes == 2048

    with pytest.raises(ValueError, match="Input should be greater than 0"):
        DataLimit(bytes=-1024)


def test_server_model_serialization():
    server_data = {
        "name": "Test Server",
        "serverId": "12345",
        "metricsEnabled": True,
        "createdTimestampMs": 1633024800000,
        "version": "1.0.0",
        "portForNewAccessKeys": 8388,
        "hostnameForAccessKeys": "vpn.example.com",
        "accessKeyDataLimit": {"bytes": 1024}
    }

    server = Server(**server_data)
    serialized = server.model_dump(by_alias=True)
    assert serialized["serverId"] == "12345"
    assert serialized["metricsEnabled"] is True
    assert serialized["accessKeyDataLimit"]["bytes"] == 1024


def test_access_key_port_validation():
    access_key = AccessKey(
        id=1,
        name="Test Key",
        password="password123",
        port=1026,
        method="aes-256-gcm",
        accessUrl="https://example.com/access-key"
    )
    assert access_key.port == 1026

    with pytest.raises(ValidationError):
        AccessKey(
            id=1,
            name="Test Key",
            password="password123",
            port=1024,
            method="aes-256-gcm",
            accessUrl="https://example.com/access-key"
        )
