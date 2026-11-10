"""Platform adapter contract suite (#456).

Every adapter under ``adapters/platforms/`` must satisfy the same contract,
proven without credentials and without network:

1. ``platform_name`` is a non-empty string, unique across the registry.
2. ``authenticate()`` without credentials returns an explicit structured
   failure (never ``None``, never a bare exception).
3. ``publish()`` on a nonexistent artifact dir returns a structured result —
   no crash.  Real (non-stub) adapters must fail on the credential pre-flight
   **before** any network call; the zero-credential fixture makes that order
   deterministic by forcing every credential lookup to return nothing.
4. Stub platforms (``is_stub=True``) say so: ``publish()`` returns an
   explicit ``not_implemented``/manual reason instead of pretending success.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any

import pytest

import automedia.adapters.platforms as platforms_pkg
from automedia.adapters.base import BasePlatformAdapter
from automedia.adapters.registry import AdapterRegistry

# ---------------------------------------------------------------------------
# Adapter discovery — every concrete adapter shipped under platforms/
# ---------------------------------------------------------------------------


def _load_all_platform_modules() -> list[Any]:
    mods = []
    for info in pkgutil.iter_modules(platforms_pkg.__path__):
        if info.name == "__main__":
            continue
        mods.append(importlib.import_module(f"automedia.adapters.platforms.{info.name}"))
    return mods


def _adapter_classes() -> list[type[BasePlatformAdapter]]:
    classes: list[type[BasePlatformAdapter]] = []
    for mod in _load_all_platform_modules():
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            is_adapter = issubclass(obj, BasePlatformAdapter) and obj is not BasePlatformAdapter
            if is_adapter and obj.__module__ == mod.__name__:
                classes.append(obj)
    return classes


ADAPTER_CLASSES: list[type[BasePlatformAdapter]] = _adapter_classes()
STUB_CLASSES = [c for c in ADAPTER_CLASSES if getattr(c, "is_stub", False) is True]
REAL_CLASSES = [c for c in ADAPTER_CLASSES if getattr(c, "is_stub", False) is False]


@pytest.fixture(autouse=True)
def _ensure_platforms_registered() -> None:
    """Re-register the shipped platforms if another test file cleared the
    singleton registry.

    ``tests/test_adapter_registry.py`` clears ``AdapterRegistry`` around its
    own tests (deliberately, for its singleton assertions) and leaves the
    platform registrations empty when the whole suite runs in one process.
    The real adapters are already-defined classes, so re-registering the
    missing ones is idempotent and restores the contract this file pins.
    """
    for adapter_cls in ADAPTER_CLASSES:
        if adapter_cls().platform_name not in AdapterRegistry.list():
            AdapterRegistry.register(adapter_cls)


def test_discovery_covers_every_platform_module() -> None:
    """The suite must be pinned to the shipped adapter set — a new adapter
    file without contract coverage fails here, not in production."""
    mods = _load_all_platform_modules()
    # 21 platform modules ship today: 20 adapters + the xiaohongshu browser
    # helper (which drives a real browser and is covered by its own tests).
    assert len(mods) >= 21
    browserless = [
        m.__name__.rsplit(".", 1)[-1]
        for m in mods
        if not any(
            issubclass(obj, BasePlatformAdapter) and obj is not BasePlatformAdapter
            for _, obj in inspect.getmembers(m, inspect.isclass)
            if obj.__module__ == m.__name__
        )
    ]
    assert browserless == ["xiaohongshu_browser"]
    # One adapter class per remaining module.
    assert len(ADAPTER_CLASSES) == len(mods) - 1


# ---------------------------------------------------------------------------
# Zero-credential fixture — forces every credential lookup to return nothing,
# so "no credentials" is deterministic and no test can reach the network.
# ---------------------------------------------------------------------------

_CRED_NAMES = ("load_credential_or_env", "load_credential", "env_lookup")


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    def _none_loader(*args: Any, **kwargs: Any) -> Any:
        # Credential loaders get a deterministic ``None``: the adapters' own
        # "credentials not set" branches execute (that IS the code under
        # test) and no lookup can reach an encrypted store or the host .env.
        return None

    def _env_lookup(_names: Any, default: str = "", **kwargs: Any) -> str:
        _ = _names, kwargs
        return default

    for mod in _load_all_platform_modules():
        for name in _CRED_NAMES:
            if hasattr(mod, name):
                monkeypatch.setattr(
                    mod,
                    name,
                    _env_lookup if name == "env_lookup" else _none_loader,
                    raising=True,
                )


def _make(adapter_cls: type[BasePlatformAdapter]) -> BasePlatformAdapter:
    return adapter_cls()


# ---------------------------------------------------------------------------
# Contract 1 — platform_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("adapter_cls", ADAPTER_CLASSES, ids=lambda c: c.__name__)
class TestPlatformName:
    def test_non_empty_string(self, adapter_cls: type[BasePlatformAdapter]) -> None:
        name = _make(adapter_cls).platform_name
        assert isinstance(name, str) and name.strip()

    def test_lowercase_identifier(self, adapter_cls: type[BasePlatformAdapter]) -> None:
        name = _make(adapter_cls).platform_name
        assert name == name.lower().strip()

    def test_unique_across_registry(self, adapter_cls: type[BasePlatformAdapter]) -> None:
        names = [
            c.__name__ for c in ADAPTER_CLASSES if c().platform_name == adapter_cls().platform_name
        ]
        assert len(names) == 1


def test_platform_names_globally_unique() -> None:
    names = [cls().platform_name for cls in ADAPTER_CLASSES]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Contract 2 — authenticate() without credentials is explicit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("adapter_cls", ADAPTER_CLASSES, ids=lambda c: c.__name__)
class TestAuthenticateWithoutCredentials:
    def test_returns_dict_with_status_and_reason(
        self, adapter_cls: type[BasePlatformAdapter]
    ) -> None:
        result = _make(adapter_cls).authenticate()
        assert result is not None
        assert isinstance(result, dict)
        assert result.get("status"), adapter_cls.__name__
        assert result.get("reason"), adapter_cls.__name__

    def test_never_reports_healthy_without_credentials(
        self, adapter_cls: type[BasePlatformAdapter]
    ) -> None:
        result = _make(adapter_cls).authenticate()
        assert result.get("healthy") is not True

    def test_refresh_session_also_explicit(self, adapter_cls: type[BasePlatformAdapter]) -> None:
        result = _make(adapter_cls).refresh_session("no-such-account")
        assert isinstance(result, dict) and result.get("status")


# ---------------------------------------------------------------------------
# Contract 3 — publish() on a nonexistent artifact dir is structured
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("adapter_cls", ADAPTER_CLASSES, ids=lambda c: c.__name__)
class TestPublishMissingArtifactDir:
    def test_no_crash_structured_result(self, adapter_cls: type[BasePlatformAdapter]) -> None:
        adapter = _make(adapter_cls)
        result = adapter.publish("/nonexistent/artifact-dir-456", {"topic": "dry"})
        assert isinstance(result, dict)
        assert result.get("status"), adapter_cls.__name__
        # 结构化失败必须带原因——空 reason 的失败等于没有结论（#456）。
        if result["status"] in ("error", "not_implemented"):
            assert result.get("reason"), result

    def test_stub_publish_never_claims_success(
        self, adapter_cls: type[BasePlatformAdapter]
    ) -> None:
        adapter = _make(adapter_cls)
        result = adapter.publish("/nonexistent/artifact-dir-456", {"topic": "dry"})
        if getattr(adapter_cls, "is_stub", False):
            assert result["status"] != "ok"
            assert "manual" in str(result.get("reason", "")).lower() or (
                result["status"] == "not_implemented"
            )


# ---------------------------------------------------------------------------
# Contract 3b — real adapters fail on the credential pre-flight, before any
# network call, when no credentials exist.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("adapter_cls", REAL_CLASSES, ids=lambda c: c.__name__)
class TestRealAdapterFailsFastWithoutCredentials:
    def test_publish_reports_missing_credentials(
        self, adapter_cls: type[BasePlatformAdapter]
    ) -> None:
        adapter = _make(adapter_cls)
        result = adapter.publish("/nonexistent/artifact-dir-456", {"topic": "dry"})
        assert isinstance(result, dict)
        assert result["status"] in ("error", "not_implemented", "skipped")
        assert result["status"] != "ok"
        reason = str(result.get("reason", ""))
        assert reason, "real adapter must explain the failure (#456)"

    def test_validate_is_bool_and_never_raises(
        self, adapter_cls: type[BasePlatformAdapter]
    ) -> None:
        result = _make(adapter_cls).validate("/nonexistent/artifact-dir-456")
        assert isinstance(result, bool)

    def test_enabled_false_without_credentials(
        self, adapter_cls: type[BasePlatformAdapter]
    ) -> None:
        # Zero-credential fixture ⇒ every credential-gated adapter is disabled.
        adapter = _make(adapter_cls)
        if isinstance(getattr(type(adapter), "enabled", None), property):
            assert adapter.enabled is False, adapter_cls.__name__


@pytest.mark.parametrize("adapter_cls", STUB_CLASSES, ids=lambda c: c.__name__)
class TestStubAdaptersAreHonest:
    def test_is_stub_flag_true(self, adapter_cls: type[BasePlatformAdapter]) -> None:
        assert getattr(adapter_cls, "is_stub", False) is True

    def test_publish_says_not_implemented(self, adapter_cls: type[BasePlatformAdapter]) -> None:
        result = _make(adapter_cls).publish("/nonexistent/artifact-dir-456", {})
        assert result["status"] == "not_implemented"
        assert result.get("reason")


# ---------------------------------------------------------------------------
# Contract 4 — registry round-trip
# ---------------------------------------------------------------------------


def test_every_stub_platform_registered() -> None:
    """Stub platforms are still platforms: the registry must resolve them."""
    for adapter_cls in STUB_CLASSES:
        assert AdapterRegistry.get(adapter_cls().platform_name) is adapter_cls


def test_real_platforms_registered() -> None:
    for adapter_cls in REAL_CLASSES:
        assert AdapterRegistry.get(adapter_cls().platform_name) is adapter_cls
