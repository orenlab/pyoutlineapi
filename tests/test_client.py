from __future__ import annotations

import asyncio
import logging

import pytest
from pydantic import SecretStr

from pyoutlineapi.client import (
    AsyncOutlineClient,
    MultiServerManager,
    create_client,
    create_multi_server_manager,
)
from pyoutlineapi.config import OutlineClientConfig
from pyoutlineapi.exceptions import ConfigurationError


@pytest.mark.asyncio
async def test_resolve_configuration_errors():
    with pytest.raises(ConfigurationError):
        AsyncOutlineClient._resolve_configuration(None, None, "x", {})
    with pytest.raises(ConfigurationError):
        AsyncOutlineClient._resolve_configuration(None, "url", None, {})
    with pytest.raises(ConfigurationError):
        AsyncOutlineClient._resolve_configuration(
            OutlineClientConfig.create_minimal(
                api_url="https://example.com/secret",
                cert_sha256="a" * 64,
            ),
            "url",
            "cert",
            {},
        )
    with pytest.raises(ConfigurationError):
        AsyncOutlineClient._resolve_configuration(None, None, None, {})
    with pytest.raises(ConfigurationError):
        AsyncOutlineClient._resolve_configuration(None, 123, 456, {})  # type: ignore[arg-type]


def test_client_init_with_config():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
        json_format=True,
    )
    client = AsyncOutlineClient(config=config)
    assert client.config.api_url.startswith("https://example.com")
    assert client.get_sanitized_config["cert_sha256"] == "***MASKED***"
    assert client.json_format is True


def test_client_init_logs_info(caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
        enable_logging=True,
    )
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.client"):
        AsyncOutlineClient(config=config)
    assert any("Client initialized" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_server_summary(monkeypatch, access_keys_list, server_dict):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    async def fake_get_access_keys(*args, **kwargs):
        return access_keys_list

    async def fake_get_metrics_status(*args, **kwargs):
        return {"metricsEnabled": False}

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", fake_get_metrics_status)

    summary = await client.get_server_summary()
    assert summary["access_keys_count"] == 1
    assert summary["server"]["serverId"] == "srv-1"


@pytest.mark.asyncio
async def test_get_server_summary_error_branches(monkeypatch, server_dict):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fail_server(*args, **kwargs):
        raise RuntimeError("server fail")

    async def bad_keys(*args, **kwargs):
        return {"accessKeys": "bad"}

    async def metrics_enabled(*args, **kwargs):
        return {"metricsEnabled": True}

    async def transfer_fail(*args, **kwargs):
        raise RuntimeError("transfer fail")

    monkeypatch.setattr(client, "get_server_info", fail_server)
    monkeypatch.setattr(client, "get_access_keys", bad_keys)
    monkeypatch.setattr(client, "get_metrics_status", metrics_enabled)
    monkeypatch.setattr(client, "get_transfer_metrics", transfer_fail)

    summary = await client.get_server_summary()
    assert summary["healthy"] is False
    assert summary["access_keys_count"] == 0
    assert summary["metrics_enabled"] is True
    assert summary["errors"]


@pytest.mark.asyncio
async def test_get_server_summary_debug_logging(monkeypatch, caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fail_server(*args, **kwargs):
        raise RuntimeError("server fail")

    async def fail_keys(*args, **kwargs):
        raise RuntimeError("keys fail")

    async def fail_metrics(*args, **kwargs):
        raise RuntimeError("metrics fail")

    monkeypatch.setattr(client, "get_server_info", fail_server)
    monkeypatch.setattr(client, "get_access_keys", fail_keys)
    monkeypatch.setattr(client, "get_metrics_status", fail_metrics)

    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.client"):
        summary = await client.get_server_summary()
    assert summary["errors"]
    assert any("Failed to fetch server info" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_server_summary_transfer_metrics_logging(
    monkeypatch, caplog, server_dict
):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    async def fake_get_access_keys(*args, **kwargs):
        return {"accessKeys": []}

    async def metrics_enabled(*args, **kwargs):
        return {"metricsEnabled": True}

    async def transfer_fail(*args, **kwargs):
        raise RuntimeError("transfer fail")

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", metrics_enabled)
    monkeypatch.setattr(client, "get_transfer_metrics", transfer_fail)

    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.client"):
        summary = await client.get_server_summary()
    assert summary["metrics_enabled"] is True
    assert any("Failed to fetch transfer metrics" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_server_summary_metrics_response_logging(
    monkeypatch, caplog, server_dict
):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    from pyoutlineapi.models import MetricsStatusResponse

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    async def fake_get_access_keys(*args, **kwargs):
        return {"accessKeys": []}

    async def metrics_status(*args, **kwargs):
        return MetricsStatusResponse(metricsEnabled=True)

    async def transfer_fail(*args, **kwargs):
        raise RuntimeError("transfer fail")

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", metrics_status)
    monkeypatch.setattr(client, "get_transfer_metrics", transfer_fail)

    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.client"):
        summary = await client.get_server_summary()
    assert summary["metrics_enabled"] is True
    assert any("Failed to fetch transfer metrics" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_server_summary_unexpected_metrics_status(monkeypatch, server_dict):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    async def fake_get_access_keys(*args, **kwargs):
        return {"accessKeys": []}

    async def metrics_status(*args, **kwargs):
        return "bad"

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", metrics_status)

    summary = await client.get_server_summary()
    assert summary["metrics_enabled"] is False


@pytest.mark.asyncio
async def test_get_server_summary_unexpected_keys_result(monkeypatch, server_dict):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    async def bad_keys(*args, **kwargs):
        return "bad"

    async def metrics_status(*args, **kwargs):
        return {"metricsEnabled": False}

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", bad_keys)
    monkeypatch.setattr(client, "get_metrics_status", metrics_status)

    summary = await client.get_server_summary()
    assert summary["access_keys_count"] == 0


@pytest.mark.asyncio
async def test_get_server_summary_access_key_list(
    monkeypatch, access_key_dict, server_dict
):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    from pyoutlineapi.models import AccessKeyList

    async def fake_get_access_keys(*args, **kwargs):
        return AccessKeyList(accessKeys=[access_key_dict])

    async def fake_get_metrics_status(*args, **kwargs):
        return {"metricsEnabled": False}

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", fake_get_metrics_status)

    summary = await client.get_server_summary()
    assert summary["access_keys_count"] == 1


@pytest.mark.asyncio
async def test_get_server_summary_metrics_status_response(
    monkeypatch, access_key_dict, server_dict
):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    async def fake_get_access_keys(*args, **kwargs):
        return {"accessKeys": [access_key_dict]}

    from pyoutlineapi.models import MetricsStatusResponse

    async def fake_get_metrics_status(*args, **kwargs):
        return MetricsStatusResponse(metricsEnabled=True)

    async def fail_transfer(*args, **kwargs):
        raise RuntimeError("transfer fail")

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", fake_get_metrics_status)
    monkeypatch.setattr(client, "get_transfer_metrics", fail_transfer)

    summary = await client.get_server_summary()
    assert summary["metrics_enabled"] is True
    assert summary["errors"]


@pytest.mark.asyncio
async def test_get_server_summary_with_metrics(
    monkeypatch, access_keys_list, server_dict, server_metrics_dict
):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return server_dict

    async def fake_get_access_keys(*args, **kwargs):
        return access_keys_list

    async def fake_get_metrics_status(*args, **kwargs):
        return {"metricsEnabled": True}

    async def fake_get_transfer_metrics(*args, **kwargs):
        return server_metrics_dict

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", fake_get_metrics_status)
    monkeypatch.setattr(client, "get_transfer_metrics", fake_get_transfer_metrics)

    summary = await client.get_server_summary()
    assert summary["metrics_enabled"] is True
    assert "transfer_metrics" in summary


@pytest.mark.asyncio
async def test_health_check_error(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(client, "get_server_info", fail)
    data = await client.health_check()
    assert data["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_success(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def ok(*args, **kwargs):
        return {"ok": True}

    monkeypatch.setattr(client, "get_server_info", ok)
    data = await client.health_check()
    assert data["healthy"] is True


@pytest.mark.asyncio
async def test_multi_server_manager_health(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )

    async def fake_aenter(self):
        return self

    async def fake_health_check(self):
        return {"healthy": True}

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fake_aenter)
    monkeypatch.setattr(AsyncOutlineClient, "health_check", fake_health_check)

    manager = MultiServerManager([config])
    async with manager:
        results = await manager.health_check_all()
        assert list(results.values())[0]["healthy"] is True


@pytest.mark.asyncio
async def test_create_context_manager(monkeypatch):
    async def fake_aenter(self):
        return self

    async def fake_aexit(self, exc_type, exc, tb):
        return None

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fake_aenter)
    monkeypatch.setattr(AsyncOutlineClient, "__aexit__", fake_aexit)

    async with AsyncOutlineClient.create(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    ) as client:
        assert isinstance(client, AsyncOutlineClient)


@pytest.mark.asyncio
async def test_create_context_manager_with_config(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )

    async def fake_aenter(self):
        return self

    async def fake_aexit(self, exc_type, exc, tb):
        return None

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fake_aenter)
    monkeypatch.setattr(AsyncOutlineClient, "__aexit__", fake_aexit)

    async with AsyncOutlineClient.create(config=config) as client:
        assert isinstance(client, AsyncOutlineClient)


def test_create_client_function():
    client = create_client(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    assert isinstance(client, AsyncOutlineClient)


def test_from_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OUTLINE_API_URL=https://example.com/secret\n"
        "OUTLINE_CERT_SHA256=" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    client = AsyncOutlineClient.from_env(env_file=env_file)
    assert isinstance(client, AsyncOutlineClient)


@pytest.mark.asyncio
async def test_multi_server_manager_helpers(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )

    async def fake_aenter(self):
        return self

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fake_aenter)

    manager = create_multi_server_manager([config])
    async with manager:
        assert manager.server_count == 1
        assert len(manager.get_server_names()) == 1
        client = manager.get_client(0)
        assert isinstance(client, AsyncOutlineClient)
        assert manager.get_all_clients()
        assert "MultiServerManager" in repr(manager)
        assert manager.get_status_summary()["total_servers"] == 1

        # string identifier lookup
        safe_name = manager.get_server_names()[0]
        assert manager.get_client(safe_name) is client


@pytest.mark.asyncio
async def test_multi_server_manager_logging(monkeypatch, caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )

    async def fake_aenter(self):
        return self

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fake_aenter)
    manager = MultiServerManager([config])
    with caplog.at_level(logging.INFO, logger="pyoutlineapi.client"):
        async with manager:
            pass
    assert any("initialized" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_multi_server_manager_init_failure(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )

    async def fail_aenter(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fail_aenter)

    manager = MultiServerManager([config])
    with pytest.raises(ConfigurationError):
        async with manager:
            pass


def test_multi_server_manager_init_errors():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    with pytest.raises(ConfigurationError):
        MultiServerManager([])
    with pytest.raises(ConfigurationError):
        MultiServerManager([config] * 51)


@pytest.mark.asyncio
async def test_health_check_all_error_path():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    manager = MultiServerManager([config])

    class Dummy:
        async def health_check(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("fail")

    manager._clients = {"srv": Dummy()}  # type: ignore[attr-defined]
    results = await manager.health_check_all()
    assert results["srv"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_all_exception_result(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    manager = MultiServerManager([config])

    async def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    manager._clients = {"srv": object()}  # type: ignore[attr-defined]
    monkeypatch.setattr(MultiServerManager, "_health_check_single", boom)

    results = await manager.health_check_all()
    assert results["srv"]["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_health_check_single_timeout():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    manager = MultiServerManager([config])

    class SlowClient:
        async def health_check(self):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.01)
            return {"healthy": True}

    result = await manager._health_check_single("srv", SlowClient(), timeout=0.001)
    assert result["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_multi_server_manager_get_client_errors():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    manager = MultiServerManager([config])
    with pytest.raises(KeyError):
        manager.get_client("missing")
    with pytest.raises(IndexError):
        manager.get_client(1)


@pytest.mark.asyncio
async def test_multi_server_manager_aexit_clears_clients(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )

    async def fake_aenter(self):
        return self

    async def fake_aexit(self, exc_type, exc, tb):
        return None

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fake_aenter)
    monkeypatch.setattr(AsyncOutlineClient, "__aexit__", fake_aexit)

    manager = MultiServerManager([config])
    await manager.__aenter__()
    await manager.__aexit__(None, None, None)
    assert manager.get_all_clients() == []


@pytest.mark.asyncio
async def test_multi_server_manager_aexit_logs_warning(monkeypatch, caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )

    async def fake_aenter(self):
        return self

    async def bad_aexit(self, exc_type, exc, tb):
        raise RuntimeError("boom")

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", fake_aenter)
    monkeypatch.setattr(AsyncOutlineClient, "__aexit__", bad_aexit)

    manager = MultiServerManager([config])
    await manager.__aenter__()
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.client"):
        await manager.__aexit__(None, None, None)
    assert any("Shutdown completed with" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_client_status_and_repr(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return {"serverId": "s"}

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    status = client.get_status()
    assert "rate_limit" in status
    assert "AsyncOutlineClient" in repr(client)


@pytest.mark.asyncio
async def test_client_aexit_handles_errors(monkeypatch, caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    class BadAudit:
        async def shutdown(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("bad")

    async def bad_shutdown(timeout: float = 30.0):  # type: ignore[no-untyped-def]
        raise RuntimeError("fail")

    class DummySession:
        closed = False

        async def close(self):  # type: ignore[no-untyped-def]
            self.closed = True

    client._audit_logger_instance = BadAudit()  # type: ignore[assignment]
    monkeypatch.setattr(client, "shutdown", bad_shutdown)
    client._session = DummySession()  # type: ignore[assignment]
    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.client"):
        await client.__aexit__(None, None, None)
    assert client._session.closed is True


@pytest.mark.asyncio
async def test_client_aexit_emergency_cleanup_error(caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    class BadAudit:
        async def shutdown(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("shutdown fail")

    class BadSession:
        closed = False

        async def close(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("close fail")

    client._audit_logger_instance = BadAudit()  # type: ignore[assignment]
    client._session = BadSession()  # type: ignore[assignment]

    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.client"):
        await client.__aexit__(None, None, None)
    assert any("Emergency cleanup error" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_healthy_servers_missing_client(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    manager = MultiServerManager([config])

    async def fake_health_check_all(self, *args, **kwargs):
        return {"missing": {"healthy": True}}

    monkeypatch.setattr(MultiServerManager, "health_check_all", fake_health_check_all)
    healthy = await manager.get_healthy_servers()
    assert healthy == []


@pytest.mark.asyncio
async def test_get_healthy_servers_filters(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    manager = MultiServerManager([config])

    class DummyClient:
        is_connected = True

    manager._clients = {"srv": DummyClient()}  # type: ignore[attr-defined]

    async def fake_health_check_all(self, *args, **kwargs):
        return {"srv": {"healthy": True}}

    monkeypatch.setattr(MultiServerManager, "health_check_all", fake_health_check_all)
    healthy = await manager.get_healthy_servers()
    assert healthy


@pytest.mark.asyncio
async def test_health_check_access_key_list_and_metrics(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    from pyoutlineapi.models import AccessKey, AccessKeyList, MetricsStatusResponse

    async def fake_get_server_info(*args, **kwargs):
        return {"serverId": "srv"}

    async def fake_get_access_keys(*args, **kwargs):
        key = AccessKey(
            id="key-1",
            name="Name",
            password="pwd",
            port=12345,
            method="aes-256-gcm",
            accessUrl="ss://example",
            dataLimit=None,
        )
        return AccessKeyList(accessKeys=[key])

    async def fake_get_metrics_status(*args, **kwargs):
        return MetricsStatusResponse(metricsEnabled=True)

    async def fake_get_transfer_metrics(*args, **kwargs):
        return {"bytesTransferredByUserId": {"key-1": 10}}

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", fake_get_metrics_status)
    monkeypatch.setattr(client, "get_transfer_metrics", fake_get_transfer_metrics)

    summary = await client.get_server_summary()
    assert summary["access_keys_count"] == 1
    assert summary["metrics_enabled"] is True
    assert "transfer_metrics" in summary


@pytest.mark.asyncio
async def test_get_server_summary_dict_keys_and_metrics(monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return {"serverId": "srv"}

    async def fake_get_access_keys(*args, **kwargs):
        return {"accessKeys": [{"id": "k1"}]}

    async def fake_get_metrics_status(*args, **kwargs):
        return {"metricsEnabled": False}

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", fake_get_metrics_status)

    summary = await client.get_server_summary()
    assert summary["access_keys_count"] == 1
    assert summary["metrics_enabled"] is False


@pytest.mark.asyncio
async def test_get_server_summary_metrics_status_error(monkeypatch, caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    async def fake_get_server_info(*args, **kwargs):
        return {"serverId": "srv"}

    async def fake_get_access_keys(*args, **kwargs):
        return {"accessKeys": []}

    async def fake_get_metrics_status(*args, **kwargs):
        raise RuntimeError("metrics fail")

    monkeypatch.setattr(client, "get_server_info", fake_get_server_info)
    monkeypatch.setattr(client, "get_access_keys", fake_get_access_keys)
    monkeypatch.setattr(client, "get_metrics_status", fake_get_metrics_status)

    with caplog.at_level(logging.DEBUG, logger="pyoutlineapi.client"):
        summary = await client.get_server_summary()
    assert summary["errors"]


@pytest.mark.asyncio
async def test_client_aexit_cleanup_logs_warning(caplog, monkeypatch):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    client = AsyncOutlineClient(config=config)

    class BadAudit:
        async def shutdown(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("audit fail")

    async def bad_shutdown(timeout: float = 30.0):  # type: ignore[no-untyped-def]
        raise RuntimeError("shutdown fail")

    class DummySession:
        closed = False

        async def close(self):  # type: ignore[no-untyped-def]
            self.closed = True

    client._audit_logger_instance = BadAudit()  # type: ignore[assignment]
    monkeypatch.setattr(client, "shutdown", bad_shutdown)
    client._session = DummySession()  # type: ignore[assignment]

    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.client"):
        await client.__aexit__(None, None, None)
    assert any("Cleanup completed with" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_multi_server_manager_aenter_logs_warning(monkeypatch, caplog):
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    manager = MultiServerManager([config])

    async def bad_enter(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("fail")

    monkeypatch.setattr(AsyncOutlineClient, "__aenter__", bad_enter)
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.client"):
        with pytest.raises(ConfigurationError):
            async with manager:
                pass
    assert any("Failed to initialize server" in r.message for r in caplog.records)
