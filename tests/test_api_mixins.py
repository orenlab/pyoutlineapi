from __future__ import annotations

from typing import cast

import pytest

from pyoutlineapi.api_mixins import (
    AccessKeyMixin,
    DataLimitMixin,
    MetricsMixin,
    ServerMixin,
)
from pyoutlineapi.common_types import JsonDict, Validators
from pyoutlineapi.models import (
    AccessKey,
    AccessKeyList,
    DataLimit,
    ExperimentalMetrics,
    MetricsStatusResponse,
    Server,
    ServerMetrics,
)


class FakeClient(ServerMixin, AccessKeyMixin, DataLimitMixin, MetricsMixin):
    def __init__(self, data):
        self._data = data
        self._default_json_format = False
        self._audit_logger_instance = None

    async def _request(self, method: str, endpoint: str, *, json=None, params=None):
        key = (method, endpoint)
        if key in self._data:
            return self._data[key]
        # Support access-key specific routes
        if endpoint.startswith("access-keys/"):
            if endpoint.endswith("/name") or endpoint.endswith("/data-limit"):
                return {"success": True}
            return self._data.get(("GET", "access-keys/{id}"), {})
        return {}


@pytest.mark.asyncio
async def test_access_keys_and_server(access_key_dict, access_keys_list, server_dict):
    data = {
        ("GET", "access-keys"): access_keys_list,
        ("GET", "access-keys/{id}"): access_key_dict,
        ("POST", "access-keys"): access_key_dict,
        ("GET", "server"): server_dict,
        ("PUT", "name"): {"success": True},
        ("PUT", "server/hostname-for-access-keys"): {"success": True},
        ("PUT", "server/port-for-new-access-keys"): {"success": True},
    }
    client = FakeClient(data)

    server = cast(Server, await client.get_server_info())
    assert server.server_id == "srv-1"

    key = cast(AccessKey, await client.create_access_key(name="Alice", port=12345))
    assert key.id == "key-1"

    key2 = cast(AccessKey, await client.create_access_key_with_id("key-2", name="Bob"))
    assert key2.id == "key-1"

    keys = cast(AccessKeyList, await client.get_access_keys())
    assert keys.count == 1

    assert await client.rename_access_key("key-1", "New") is True
    assert await client.rename_server("Server") is True
    assert await client.set_hostname("example.com") is True
    assert await client.set_default_port(23456) is True
    assert await client.delete_access_key("key-1") is True
    assert await client.set_access_key_data_limit("key-1", DataLimit(bytes=1)) is True
    assert await client.remove_access_key_data_limit("key-1") is True
    key_single = cast(AccessKey, await client.get_access_key("key-1"))
    assert key_single.id == "key-1"

    server_json = cast(JsonDict, await client.get_server_info(as_json=True))
    assert server_json["serverId"] == "srv-1"

    # AuditableMixin fallback path (remove instance logger to force fallback)
    del client.__dict__["_audit_logger_instance"]
    assert client._audit_logger is not None


@pytest.mark.asyncio
async def test_set_hostname_validation_error():
    client = FakeClient({})
    with pytest.raises(ValueError, match=r".*"):
        await client.set_hostname(" ")


@pytest.mark.asyncio
async def test_limits_and_metrics(server_metrics_dict, experimental_metrics_dict):
    data = {
        ("GET", "metrics/transfer"): server_metrics_dict,
        ("GET", "metrics/enabled"): {"metricsEnabled": True},
        ("PUT", "metrics/enabled"): {"metricsEnabled": True},
        ("GET", "experimental/server/metrics"): experimental_metrics_dict,
    }
    client = FakeClient(data)

    limit = DataLimit(bytes=1024)
    assert await client.set_global_data_limit(limit) is True
    assert await client.remove_global_data_limit() is True

    status = cast(MetricsStatusResponse, await client.get_metrics_status())
    assert status.metrics_enabled is True

    status_json = cast(JsonDict, await client.get_metrics_status(as_json=True))
    assert status_json["metricsEnabled"] is True

    status_set = await client.set_metrics_status(True)
    assert status_set is True

    metrics = cast(ServerMetrics, await client.get_transfer_metrics())
    assert metrics.total_bytes == 300

    exp = cast(ExperimentalMetrics, await client.get_experimental_metrics("1h"))
    assert exp.get_key_metric("key-1") is not None

    assert Validators.validate_since("1h") == "1h"
