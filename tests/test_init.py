from __future__ import annotations

from importlib import reload
from typing import Any

import pytest

import pyoutlineapi


def test_get_version_monkeypatch(monkeypatch):
    monkeypatch.setattr(pyoutlineapi, "__version__", "9.9.9")
    assert pyoutlineapi.get_version() == "9.9.9"


def test_quick_setup_prints(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called: dict[str, Any] = {"value": False}

    def fake_create_env_template() -> None:
        called["value"] = True

    monkeypatch.setattr(pyoutlineapi, "create_env_template", fake_create_env_template)
    pyoutlineapi.quick_setup()
    out = capsys.readouterr().out
    assert called["value"] is True
    assert "Created .env.example" in out


def test_print_type_info(monkeypatch, capsys):
    pyoutlineapi.print_type_info()
    out = capsys.readouterr().out
    assert "PyOutlineAPI Type Aliases" in out
    assert "AuditLogger" in out


def test_getattr_helpful_errors():
    with pytest.raises(AttributeError) as exc:
        _ = pyoutlineapi.OutlineClient
    assert "AsyncOutlineClient" in str(exc.value)

    with pytest.raises(AttributeError) as exc:
        _ = pyoutlineapi.NonExistentThing
    assert "has no attribute" in str(exc.value)


def test_version_fallback(monkeypatch):
    import pyoutlineapi as module

    def raise_not_found(_name: str) -> str:
        raise module.metadata.PackageNotFoundError

    monkeypatch.setattr(module.metadata, "version", raise_not_found)
    reloaded = reload(module)
    assert reloaded.__version__ == "0.4.0-dev"
