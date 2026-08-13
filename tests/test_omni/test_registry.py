"""Tests for OmniToolRegistry singleton and CRUD."""

from __future__ import annotations

import pytest

from automedia.omni.base import BaseOmniAdapter
from automedia.omni.registry import OmniToolRegistry


class _StubAdapter(BaseOmniAdapter):
    @property
    def name(self) -> str:
        return "stub"

    def validate_env(self) -> bool:
        return True


class _StubAdapter2(BaseOmniAdapter):
    @property
    def name(self) -> str:
        return "stub2"

    def validate_env(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    OmniToolRegistry.clear()


class TestOmniToolRegistrySingleton:
    def test_singleton_returns_same_instance(self) -> None:
        r1 = OmniToolRegistry()
        r2 = OmniToolRegistry()
        assert r1 is r2


class TestOmniToolRegistryCRUD:
    def test_register_and_get(self) -> None:
        adapter = _StubAdapter()
        OmniToolRegistry.register(adapter)
        got = OmniToolRegistry.get("stub")
        assert got is adapter

    def test_list_returns_registered_names(self) -> None:
        OmniToolRegistry.register(_StubAdapter())
        OmniToolRegistry.register(_StubAdapter2())
        names = OmniToolRegistry.list_tools()
        assert names == ["stub", "stub2"]

    def test_clear_removes_all_adapters(self) -> None:
        OmniToolRegistry.register(_StubAdapter())
        assert OmniToolRegistry.list_tools() == ["stub"]
        OmniToolRegistry.clear()
        assert OmniToolRegistry.list_tools() == []

    def test_list_tools_returns_registered_names(self) -> None:
        OmniToolRegistry.register(_StubAdapter())
        OmniToolRegistry.register(_StubAdapter2())
        names = OmniToolRegistry.list_tools()
        assert names == ["stub", "stub2"]

    def test_register_raises_value_error_for_empty_name(self) -> None:
        class _EmptyNameAdapter(BaseOmniAdapter):
            @property
            def name(self) -> str:
                return ""

            def validate_env(self) -> bool:
                return True

        with pytest.raises(ValueError, match="must be a non-empty string"):
            OmniToolRegistry.register(_EmptyNameAdapter())

    def test_register_raises_key_error_for_duplicate(self) -> None:
        OmniToolRegistry.register(_StubAdapter())
        with pytest.raises(KeyError, match="already registered"):
            OmniToolRegistry.register(_StubAdapter())

    def test_get_raises_key_error_for_unknown(self) -> None:
        with pytest.raises(KeyError, match="No adapter registered for 'nonexistent'"):
            OmniToolRegistry.get("nonexistent")

    def test_auto_registration_via_register_builtins(self) -> None:
        """Verify _register_builtins() registers opp, ol, orf."""
        from automedia.omni import _register_builtins

        OmniToolRegistry.clear()  # clear after autouse fixture
        _register_builtins()
        names = OmniToolRegistry.list_tools()
        assert "opp" in names
        assert "ol" in names
        assert "orf" in names
        assert len(names) == 3


# Module-level: verify auto-registration runs when __init__.py is imported
# This assertion runs during test collection, before any autouse fixture.
_ = OmniToolRegistry()
assert "opp" in OmniToolRegistry._registry, (
    f"Auto-registration: opp not found in {list(OmniToolRegistry._registry.keys())}"
)
assert "ol" in OmniToolRegistry._registry, (
    f"Auto-registration: ol not found in {list(OmniToolRegistry._registry.keys())}"
)
assert "orf" in OmniToolRegistry._registry, (
    f"Auto-registration: orf not found in {list(OmniToolRegistry._registry.keys())}"
)
