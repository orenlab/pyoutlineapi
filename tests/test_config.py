from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import SecretStr

from pyoutlineapi.config import (
    DevelopmentConfig,
    OutlineClientConfig,
    ProductionConfig,
    create_env_template,
    load_config,
)
from pyoutlineapi.exceptions import ConfigurationError


def _write_env(path: Path) -> None:
    path.write_text(
        """
OUTLINE_API_URL=https://example.com/secret
OUTLINE_CERT_SHA256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
OUTLINE_TIMEOUT=15
""".strip(),
        encoding="utf-8",
    )


def test_from_env_and_sanitized(tmp_path: Path):
    env_file = tmp_path / ".env"
    _write_env(env_file)
    config = OutlineClientConfig.from_env(env_file=env_file)
    assert config.api_url.startswith("https://example.com")
    assert config.timeout == 15
    sanitized = config.get_sanitized_config
    assert sanitized["cert_sha256"] == "***MASKED***"
    assert "secret" not in sanitized["api_url"]


def test_from_env_str_path(tmp_path: Path):
    env_file = tmp_path / ".env"
    _write_env(env_file)
    config = OutlineClientConfig.from_env(env_file=str(env_file))
    assert config.api_url.startswith("https://example.com")


def test_create_minimal():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
        timeout=20,
    )
    assert config.timeout == 20
    assert isinstance(config.cert_sha256, SecretStr)

    with pytest.raises(TypeError):
        OutlineClientConfig.create_minimal(
            api_url="https://example.com/secret",
            cert_sha256=123,  # type: ignore[arg-type]
        )

    config2 = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
    )
    assert isinstance(config2.cert_sha256, SecretStr)


def test_load_config_variants(monkeypatch):
    monkeypatch.setenv("DEV_OUTLINE_API_URL", "https://example.com/secret")
    monkeypatch.setenv("DEV_OUTLINE_CERT_SHA256", "a" * 64)
    monkeypatch.setenv("PROD_OUTLINE_API_URL", "https://example.com/secret")
    monkeypatch.setenv("PROD_OUTLINE_CERT_SHA256", "a" * 64)
    config = load_config(
        "development",
        timeout=11,
    )
    assert isinstance(config, DevelopmentConfig)
    config = load_config(
        "production",
        timeout=12,
    )
    assert isinstance(config, ProductionConfig)

    with pytest.raises(ValueError):
        load_config("nope")

    monkeypatch.setenv("OUTLINE_API_URL", "https://example.com/secret")
    monkeypatch.setenv("OUTLINE_CERT_SHA256", "a" * 64)
    config = load_config("custom")
    assert isinstance(config, OutlineClientConfig)


def test_load_config_unknown_env_branch(monkeypatch):
    from pyoutlineapi import config as config_module

    monkeypatch.setenv("OUTLINE_API_URL", "https://example.com/secret")
    monkeypatch.setenv("OUTLINE_CERT_SHA256", "a" * 64)
    monkeypatch.setattr(
        config_module,
        "_VALID_ENVIRONMENTS",
        frozenset({"development", "production", "custom", "staging"}),
    )
    config = load_config("staging")
    assert isinstance(config, OutlineClientConfig)


def test_create_env_template(tmp_path: Path):
    target = tmp_path / "template.env"
    create_env_template(target)
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "OUTLINE_API_URL" in content

    target2 = tmp_path / "template2.env"
    create_env_template(str(target2))
    assert target2.exists()


def test_create_env_template_invalid_path():
    with pytest.raises(TypeError):
        create_env_template(123)  # type: ignore[arg-type]


def test_model_copy_and_circuit_config():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
        enable_circuit_breaker=True,
        circuit_failure_threshold=2,
    )
    copied = config.model_copy_immutable(timeout=12)
    assert copied.timeout == 12
    assert copied.circuit_config is not None

    with pytest.raises(ValueError):
        config.model_copy_immutable(bad_key=1)  # type: ignore[arg-type]

    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
        enable_circuit_breaker=False,
    )
    assert config.circuit_config is None


def test_cert_sha_assignment_guard():
    config = OutlineClientConfig.create_minimal(
        api_url="https://example.com/secret",
        cert_sha256="a" * 64,
    )
    with pytest.raises(TypeError):
        config.cert_sha256 = "bad"  # type: ignore[assignment]
    config.cert_sha256 = SecretStr("a" * 64)


def test_user_agent_control_chars():
    with pytest.raises(ValueError):
        OutlineClientConfig.create_minimal(
            api_url="https://example.com/secret",
            cert_sha256="a" * 64,
            user_agent="bad\u0001",
        )


def test_validate_config_http_warning_and_circuit_adjust(caplog):
    with caplog.at_level(logging.WARNING, logger="pyoutlineapi.config"):
        config = OutlineClientConfig.create_minimal(
            api_url="http://example.com/secret",
            cert_sha256="a" * 64,
            enable_circuit_breaker=True,
            circuit_call_timeout=0.1,
        )
    assert config.circuit_call_timeout >= config._get_max_request_time()
    assert any("Using HTTP" in r.message for r in caplog.records)


def test_from_env_errors(tmp_path: Path, monkeypatch):
    with pytest.raises(ConfigurationError):
        OutlineClientConfig.from_env(env_file=tmp_path / "missing.env")

    with pytest.raises(TypeError):
        OutlineClientConfig.from_env(env_file=123)  # type: ignore[arg-type]

    # env_file None uses environment
    monkeypatch.setenv("OUTLINE_API_URL", "https://example.com/secret")
    monkeypatch.setenv("OUTLINE_CERT_SHA256", "a" * 64)
    config = OutlineClientConfig.from_env()
    assert isinstance(config, OutlineClientConfig)


def test_production_config_security(monkeypatch):
    monkeypatch.setenv("PROD_OUTLINE_API_URL", "http://example.com/secret")
    monkeypatch.setenv("PROD_OUTLINE_CERT_SHA256", "a" * 64)
    with pytest.raises(ConfigurationError):
        load_config("production")

    monkeypatch.setenv("PROD_OUTLINE_API_URL", "https://example.com/secret")
    monkeypatch.setenv("PROD_OUTLINE_CERT_SHA256", "a" * 64)
    config = ProductionConfig(
        api_url="https://example.com/secret",
        cert_sha256=SecretStr("a" * 64),
        enable_circuit_breaker=False,
    )
    assert config.enable_circuit_breaker is False
    assert config.allow_private_networks is False
    assert config.resolve_dns_for_ssrf is True
