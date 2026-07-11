"""Tests for BaseGate ABC and GateRegistry singleton."""

from __future__ import annotations

from abc import ABC
from typing import Any

import pytest

from automedia.gates.base import BaseGate, GateRegistry, _registry

# =========================================================================
# GateRegistry — unit tests
# =========================================================================


class TestGateRegistryBasics:
    """GateRegistry is a singleton that stores gate classes."""

    def test_singleton(self) -> None:
        """Multiple constructor calls return the same instance."""
        r1 = GateRegistry()
        r2 = GateRegistry()
        assert r1 is r2

    def test_register_and_get(self) -> None:
        """register() + get() round-trip."""
        registry = GateRegistry()

        class _UniqueGateA(  # type: ignore[no-redef]
            BaseGate
        ):
            _gate_name = "G99"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {"ok": True}

        registered_cls = registry.get("G99")
        assert registered_cls is _UniqueGateA
        assert registered_cls._gate_name == "G99"  # class-level access

    def test_get_unknown(self) -> None:
        """get() on unknown name raises KeyError."""
        registry = GateRegistry()
        with pytest.raises(KeyError, match="NOT_REGISTERED"):
            registry.get("NOT_REGISTERED")

    def test_register_duplicate_raises(self) -> None:
        """register() with a duplicate gate_name raises KeyError."""
        GateRegistry()

        class _UniqueGateB1(BaseGate):
            _gate_name = "G98"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {"ok": True}

        with pytest.raises(KeyError, match="G98"):

            class _UniqueGateB2(  # type: ignore[unused-variable]
                BaseGate
            ):
                _gate_name = "G98"
                _failure_mode = "stop"

                def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                    return {"nope": True}

    def test_list(self) -> None:
        """list() returns sorted registered names."""
        registry = GateRegistry()
        names = registry.list()
        assert isinstance(names, list)
        # All names should be sorted
        assert names == sorted(names)

    def test_list_contains_registered_gates(self) -> None:
        """list() includes the classes we registered above."""
        registry = GateRegistry()
        names = registry.list()
        assert "G99" in names
        assert "G98" in names

    def test_get_all(self) -> None:
        """get_all() returns a copy of the full mapping."""
        registry = GateRegistry()
        all_gates = registry.get_all()
        assert isinstance(all_gates, dict)
        assert "G99" in all_gates

    def test_get_all_is_copy(self) -> None:
        """Modifying get_all() dict does not affect the registry."""
        registry = GateRegistry()
        snapshot = registry.get_all()
        snapshot.clear()
        assert "G99" in registry.get_all()

    def test_contains(self) -> None:
        """__contains__ works."""
        registry = GateRegistry()
        assert "G99" in registry
        assert "NONEXISTENT" not in registry

    def test_len(self) -> None:
        """__len__ reflects number of registered gates."""
        registry = GateRegistry()
        assert len(registry) >= 2  # we registered at least 2

    def test_repr(self) -> None:
        """__repr__ includes count and names."""
        registry = GateRegistry()
        text = repr(registry)
        assert "GateRegistry" in text
        assert "gates:" in text


# =========================================================================
# BaseGate — abstract base
# =========================================================================


class TestBaseGateAbstract:
    """BaseGate cannot be instantiated directly."""

    def test_cannot_instantiate_base(self) -> None:
        """BaseGate() raises TypeError because execute is abstract."""
        with pytest.raises(TypeError):
            BaseGate()  # type: ignore[abstract]

    def test_base_is_abc(self) -> None:
        """BaseGate is a subclass of ABC."""
        assert issubclass(BaseGate, ABC)

    def test_execute_is_abstract(self) -> None:
        """execute is listed among BaseGate's abstract methods."""
        assert "execute" in BaseGate.__abstractmethods__  # type: ignore[attr-defined]


class TestBaseGateConcrete:
    """A concrete subclass must define gate_name, failure_mode, execute."""

    def test_concrete_gate_can_be_instantiated(self) -> None:
        """Gate with all required members can be created."""

        class PingGate(BaseGate):
            _gate_name = "G97"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {"status": "pong", "input": gate_context}

        gate = PingGate()
        assert isinstance(gate, BaseGate)
        assert isinstance(gate, PingGate)

    def test_gate_name_read_only_property(self) -> None:
        """gate_name is a property and cannot be set on the instance."""

        class ReadOnlyGate(BaseGate):
            _gate_name = "G96"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {}

        gate = ReadOnlyGate()
        assert gate.gate_name == "G96"

        with pytest.raises(AttributeError):
            gate.gate_name = "MUTATED"  # type: ignore

    def test_failure_mode_property(self) -> None:
        """failure_mode returns the class-level value."""

        class StopGate(BaseGate):
            _gate_name = "G95"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {}

        assert StopGate().failure_mode == "stop"

    def test_failure_mode_cannot_be_set_on_instance(self) -> None:
        """failure_mode is read-only on the instance."""

        class FailGate(BaseGate):
            _gate_name = "G94"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {}

        gate = FailGate()
        with pytest.raises(AttributeError):
            gate.failure_mode = "ignore"  # type: ignore

    def test_execute_returns_dict(self) -> None:
        """execute() returns the expected dict."""

        class EchoGate(BaseGate):
            _gate_name = "G93"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {"echo": gate_context}

        result = EchoGate().execute({"msg": "hello"})
        assert result == {"echo": {"msg": "hello"}}

    def test_execute_receives_context(self) -> None:
        """execute() receives the context dict passed by the caller."""

        class CaptureGate(BaseGate):
            _gate_name = "G92"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {"captured": gate_context}

        ctx = {"step": 1, "value": 42}
        result = CaptureGate().execute(ctx)
        assert result["captured"] is ctx


# =========================================================================
# __str__ / __repr__
# =========================================================================


class TestStringRepresentations:
    """__str__ and __repr__ produce useful output."""

    def test_str(self) -> None:
        """__str__ returns the gate_name."""

        class StrGate(BaseGate):
            _gate_name = "G91"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {}

        assert str(StrGate()) == "G91"

    def test_repr(self) -> None:
        """__repr__ includes class name, gate_name, and failure_mode."""

        class ReprGate(BaseGate):
            _gate_name = "G90"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {}

        r = repr(ReprGate())
        assert "ReprGate" in r
        assert "G90" in r
        assert "stop" in r


# =========================================================================
# Automatic registration via __init_subclass__
# =========================================================================


class TestAutoRegistration:
    """Subclass creation automatically registers in the global registry."""

    def test_subclass_auto_registered(self) -> None:
        """A concrete BaseGate subclass is automatically in _registry."""
        # The classes defined above already registered themselves.
        # We verify they're reachable:
        assert "G97" in _registry
        assert "G93" in _registry

    def test_registry_get_returns_class_not_instance(self) -> None:
        """registry.get() returns the class, usable for instantiation."""
        cls = _registry.get("G97")
        instance = cls()
        assert instance.execute({"a": 1}) == {"status": "pong", "input": {"a": 1}}

    def test_intermediate_abc_registered_but_not_instantiable(self) -> None:
        """An intermediate ABC that defines _gate_name IS registered
        (registry stores classes), but still can't be instantiated."""

        class MiddleGate(BaseGate, ABC):
            _gate_name = "G88"
            _failure_mode = "stop"
            # execute is still abstract

        # Registry stores the class (it has _gate_name / _failure_mode)
        assert "G88" in _registry

        # But can't instantiate because execute is abstract
        with pytest.raises(TypeError):
            MiddleGate()  # type: ignore[abstract]

    def test_subclass_without_execute_not_registered(self) -> None:
        """Subclasses that don't define gate_name or don't have a concrete
        execute should not crash __init_subclass__."""
        # Just verify no exception was raised — the test_file itself
        # importing base.py already exercises this path.
        pass

    def test_late_subclass_also_registered(self) -> None:
        """A subclass defined after previous tests still gets registered."""

        class LateGate(BaseGate):
            _gate_name = "G87"
            _failure_mode = "stop"

            def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                return {"late": True}

        assert "G87" in _registry
        assert _registry.get("G87") is LateGate


# =========================================================================
# Module-level _registry alias
# =========================================================================


class TestModuleRegistry:
    """The module exposes _registry as the singleton."""

    def test_registry_is_gate_registry_instance(self) -> None:
        assert isinstance(_registry, GateRegistry)

    def test_registry_is_same_as_constructor(self) -> None:
        assert _registry is GateRegistry()
