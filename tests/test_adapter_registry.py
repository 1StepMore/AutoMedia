"""Tests for AdapterRegistry singleton."""

from __future__ import annotations

from typing import Any

import pytest

from automedia.adapters.base import BasePlatformAdapter
from automedia.adapters.registry import AdapterRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _StubAdapterA(BasePlatformAdapter):
    @property
    def platform_name(self) -> str:
        return "stub_a"

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict:
        return {"status": "ok"}


class _StubAdapterB(BasePlatformAdapter):
    @property
    def platform_name(self) -> str:
        return "stub_b"

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict:
        return {"status": "ok"}


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """Clear the singleton registry before each test."""
    AdapterRegistry.clear()
    yield


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_same_instance(self) -> None:
        r1 = AdapterRegistry()
        r2 = AdapterRegistry()
        assert r1 is r2

    def test_class_and_instance_share_registry(self) -> None:
        r = AdapterRegistry()
        AdapterRegistry.register(_StubAdapterA)
        assert "stub_a" in AdapterRegistry.list()
        assert "stub_a" in r.list()


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_single(self) -> None:
        AdapterRegistry.register(_StubAdapterA)
        assert AdapterRegistry.list() == ["stub_a"]

    def test_register_multiple(self) -> None:
        AdapterRegistry.register(_StubAdapterA)
        AdapterRegistry.register(_StubAdapterB)
        assert AdapterRegistry.list() == ["stub_a", "stub_b"]

    def test_register_duplicate_raises(self) -> None:
        AdapterRegistry.register(_StubAdapterA)
        with pytest.raises(KeyError, match="already registered"):
            AdapterRegistry.register(_StubAdapterA)  # same class again

    def test_register_duplicate_name_different_class(self) -> None:
        class _AnotherA(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "stub_a"  # same name

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict:
                return {"status": "ok"}

        AdapterRegistry.register(_StubAdapterA)
        with pytest.raises(KeyError, match="already registered"):
            AdapterRegistry.register(_AnotherA)

    def test_register_empty_name_raises(self) -> None:
        class _EmptyName(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return ""

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict:
                return {"status": "ok"}

        with pytest.raises(ValueError, match="non-empty"):
            AdapterRegistry.register(_EmptyName)


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_existing(self) -> None:
        AdapterRegistry.register(_StubAdapterA)
        cls = AdapterRegistry.get("stub_a")
        assert cls is _StubAdapterA

    def test_get_missing_raises(self) -> None:
        with pytest.raises(KeyError, match="No adapter registered"):
            AdapterRegistry.get("nonexistent")

    def test_get_returns_class_not_instance(self) -> None:
        AdapterRegistry.register(_StubAdapterA)
        cls = AdapterRegistry.get("stub_a")
        instance = cls()
        assert isinstance(instance, _StubAdapterA)
        assert instance.platform_name == "stub_a"


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestList:
    def test_empty_after_clear(self) -> None:
        assert AdapterRegistry.list() == []

    def test_list_returns_sorted(self) -> None:
        AdapterRegistry.register(_StubAdapterB)  # "stub_b"
        AdapterRegistry.register(_StubAdapterA)  # "stub_a"
        assert AdapterRegistry.list() == ["stub_a", "stub_b"]


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_all(self) -> None:
        AdapterRegistry.register(_StubAdapterA)
        AdapterRegistry.register(_StubAdapterB)
        assert len(AdapterRegistry.list()) == 2
        AdapterRegistry.clear()
        assert AdapterRegistry.list() == []


class TestListPublishablePlatforms:
    def test_method_exists(self) -> None:
        r = AdapterRegistry()
        assert hasattr(r, "list_publishable_platforms")

    def test_returns_empty_after_clear(self) -> None:
        r = AdapterRegistry()
        AdapterRegistry.clear()
        assert r.list_publishable_platforms() == []

    def test_returns_is_stub_from_class_attribute(self) -> None:
        AdapterRegistry.register(_StubAdapterA)
        AdapterRegistry.register(_StubAdapterB)
        platforms = AdapterRegistry().list_publishable_platforms()
        assert len(platforms) == 2
        for p in platforms:
            assert "name" in p
            assert "is_stub" in p
        assert all(p["is_stub"] is True for p in platforms)

    def test_preserves_is_stub_false(self) -> None:
        class _RealAdapter(BasePlatformAdapter):
            is_stub = False

            @property
            def platform_name(self) -> str:
                return "real_platform"

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict:
                return {"status": "ok"}

        AdapterRegistry.register(_RealAdapter)
        platforms = AdapterRegistry().list_publishable_platforms()
        assert platforms == [{"name": "real_platform", "is_stub": False}]

    def test_returns_sorted(self) -> None:
        AdapterRegistry.register(_StubAdapterB)
        AdapterRegistry.register(_StubAdapterA)
        platforms = AdapterRegistry().list_publishable_platforms()
        assert [p["name"] for p in platforms] == ["stub_a", "stub_b"]
