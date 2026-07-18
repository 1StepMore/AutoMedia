"""Thread-safety tests for GateRegistry.

Verifies that concurrent ``register()``, ``get()``, and mixed operations
on the module-level ``_registry`` singleton don't cause race conditions,
duplicate entries, or missing registrations.

See issue #17 — these tests exercise the thread-safety gap.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

import pytest

from automedia.gates.base import BaseGate, _registry

# =========================================================================
# Helpers
# =========================================================================

# Names guaranteed not to clash with existing test gate classes
# (test_gate_base.py uses G87-G99; test_gate_engine.py uses G73-G85;
#  test_runner.py uses G60-G61 and V96-V99).
_SAFE_NAMES: list[str] = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "L98", "L99", "V90"]


def _make_test_gate(name: str) -> type[BaseGate]:
    """Build a BaseGate subclass with *name* **without** auto-registration.

    The trick: ``_gate_name`` is assigned **after** ``type()`` returns,
    so ``__init_subclass__`` (which checks ``hasattr(cls, "_gate_name")``)
    won't fire during class creation.
    """
    cls = type(
        f"_TestGate_{name}",
        (BaseGate,),
        {
            "_failure_mode": "stop",
            "execute": lambda self, ctx: {"passed": True},  # type: ignore[arg-type]
        },
    )
    # Assign after creation → __init_subclass__ will NOT auto-register
    cls._gate_name = name  # type: ignore[attr-defined]
    return cls  # type: ignore[return-value]


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def clean_registry() -> Any:
    """Save & restore ``_registry._registry`` around each test for isolation."""
    saved = dict(_registry._registry)
    _registry.clear()
    yield
    _registry.clear()
    _registry._registry.update(saved)


# =========================================================================
# Tests
# =========================================================================


class TestGateRegistryConcurrency:
    """Thread-safety verification for the shared GateRegistry singleton."""

    # ------------------------------------------------------------------
    # Test 1 — Concurrent register of 10 unique names
    # ------------------------------------------------------------------

    def test_concurrent_register_10_unique(self, clean_registry: Any) -> None:
        """10 threads each register a unique gate → all 10 present."""
        names = _SAFE_NAMES[:10]  # D1-D9, L98
        gate_classes = [_make_test_gate(n) for n in names]

        def _reg(cls: type[BaseGate]) -> str:
            _registry.register(cls)
            return cls._gate_name  # type: ignore[attr-defined]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_reg, cls) for cls in gate_classes]
            results = [f.result() for f in futures]

        # --- assertions ---
        assert len(results) == 10
        for n in names:
            assert n in _registry, f"Gate {n!r} missing after concurrent register"

    # ------------------------------------------------------------------
    # Test 2 — Concurrent get()
    # ------------------------------------------------------------------

    def test_concurrent_get_10_threads(self, clean_registry: Any) -> None:
        """10 threads call ``get()`` concurrently → correct results, no errors."""
        names = _SAFE_NAMES[:3]  # D1, D2, D3
        classes: dict[str, type[BaseGate]] = {}
        for n in names:
            cls = _make_test_gate(n)
            _registry.register(cls)
            classes[n] = cls

        # 10 callers: 3 × D1, 3 × D2, 4 × D3
        call_args = names[:1] * 3 + names[1:2] * 3 + names[2:3] * 4

        def _get(name: str) -> type[BaseGate]:
            return _registry.get(name)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_get, a) for a in call_args]
            results = [f.result() for f in futures]

        # --- assertions ---
        assert len(results) == 10
        for a, got in zip(call_args, results, strict=False):
            assert got is classes[a], (
                f"Expected {classes[a].__name__} for {a!r}, got {got.__name__}"
            )

    # ------------------------------------------------------------------
    # Test 3 — Interleaved register + get
    # ------------------------------------------------------------------

    def test_register_and_get_interleaved(self, clean_registry: Any) -> None:
        """Concurrent ``register()`` / ``get()`` → uncorrupted final state."""
        reg_names = _SAFE_NAMES[:10]
        gate_classes = [_make_test_gate(n) for n in reg_names]

        def _register_gate(cls: type[BaseGate]) -> str | None:
            try:
                _registry.register(cls)
                return cls._gate_name  # type: ignore[attr-defined]
            except (KeyError, ValueError):
                return None

        def _get_gate(name: str) -> type[BaseGate] | None:
            try:
                return _registry.get(name)
            except KeyError:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            reg_futures = [ex.submit(_register_gate, cls) for cls in gate_classes]
            get_futures = [ex.submit(_get_gate, n) for n in reg_names]
            concurrent.futures.wait(reg_futures + get_futures)

        reg_results = [f.result() for f in reg_futures]
        assert all(r is not None for r in reg_results), f"Some registers failed: {reg_results}"
        # Every registered gate must be queryable
        for n in reg_names:
            cls = _registry.get(n)
            assert cls._gate_name == n, (  # type: ignore[attr-defined]
                f"Gate {n!r} has mismatched _gate_name"
            )

    # ------------------------------------------------------------------
    # Test 4 — Same name from 2 threads
    # ------------------------------------------------------------------

    def test_register_same_name_concurrently(self, clean_registry: Any) -> None:
        """Two threads registering the same name → no corruption.

        The current ``register()`` method performs a check-then-set
        without locking, so a race window exists where both threads
        pass the uniqueness check.  This test verifies the dict remains
        consistent regardless of which thread "wins".
        """
        cls_a = _make_test_gate("D9")
        cls_b = _make_test_gate("D9")  # same name

        outcomes: list[str] = []

        def _reg(cls: type[BaseGate]) -> None:
            try:
                _registry.register(cls)
                outcomes.append("ok")
            except KeyError:
                outcomes.append("duplicate")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fa = ex.submit(_reg, cls_a)
            fb = ex.submit(_reg, cls_b)
            fa.result()
            fb.result()

        # --- assertions ---
        # At least one thread must have succeeded
        assert "ok" in outcomes, "Neither thread succeeded in registering"
        # The name must be registered exactly once
        assert "D9" in _registry, "Gate name missing after concurrent register"
        registered = _registry.get("D9")
        assert registered is not None
        # The registered class must be a valid gate with the correct name
        assert registered._gate_name == "D9"  # type: ignore[attr-defined]
        # Both outcomes are valid: "ok"+"duplicate" or "ok"+"ok" (race win)
        assert len(outcomes) == 2

    # ------------------------------------------------------------------
    # Test 5 — Clear + register concurrently
    # ------------------------------------------------------------------

    def test_clear_and_register_race(self, clean_registry: Any) -> None:
        """Internal ``_registry`` cleared while concurrent registration happens.

        The ``BaseRegistry`` exposes a ``clear()`` method (used for test
        isolation).  This test verifies that concurrent clears + registers
        don't corrupt the dict or leave dangling references.
        """
        gate_classes = [_make_test_gate(n) for n in _SAFE_NAMES]

        def _reg(cls: type[BaseGate]) -> None:
            try:
                _registry.register(cls)
            except (KeyError, ValueError):
                pass

        def _clear() -> None:
            _registry._registry.clear()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = []
            for cls in gate_classes:
                futures.append(ex.submit(_reg, cls))
            for _ in range(5):
                futures.append(ex.submit(_clear))
            concurrent.futures.wait(futures)

        # --- assertions ---
        # Final dict must be consistent: every key → class with matching name
        for name, cls in _registry._registry.items():
            assert hasattr(cls, "_gate_name"), (
                f"Gate key {name!r} maps to a class without _gate_name"
            )
            assert cls._gate_name == name, (  # type: ignore[attr-defined]
                f"Gate key {name!r} != cls._gate_name {cls._gate_name!r}"  # type: ignore[attr-defined]
            )
            assert hasattr(cls, "_failure_mode"), f"Gate {name!r} missing _failure_mode"

    # ------------------------------------------------------------------
    # Test 6 — mix of register / get / contains / len under high concurrency
    # ------------------------------------------------------------------

    def test_high_concurrency_mixed_operations(self, clean_registry: Any) -> None:
        """20 threads hammer the registry with mixed operations → stability.

        Writes (``register``) and reads (``get``, ``__contains__``,
        ``__len__``, ``list``, ``get_all``) are interleaved to stress
        the dict under contention.
        """
        # Register a few baseline gates
        baseline_names = _SAFE_NAMES[:5]
        baseline_cls = {n: _make_test_gate(n) for n in baseline_names}
        for n, cls in baseline_cls.items():
            _registry.register(cls)

        new_gates = [_make_test_gate(n) for n in _SAFE_NAMES[5:]]

        def _random_op(
            op_id: int,
        ) -> str | None:
            """Pick a random operation and run it."""
            import random

            op = random.choice(["register", "get", "contains", "len", "list", "get_all"])
            try:
                if op == "register":
                    idx = (op_id * 7) % len(new_gates)
                    _registry.register(new_gates[idx])
                    return "register"
                elif op == "get":
                    name = random.choice(baseline_names + _SAFE_NAMES[5:])
                    _registry.get(name)
                    return "get"
                elif op == "contains":
                    name = random.choice(baseline_names + _SAFE_NAMES[5:])
                    _ = name in _registry
                    return "contains"
                elif op == "len":
                    _ = len(_registry)
                    return "len"
                elif op == "list":
                    _ = _registry.list()
                    return "list"
                else:  # get_all
                    _ = _registry.get_all()
                    return "get_all"
            except KeyError:
                return f"{op}-miss"

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_random_op, i) for i in range(20)]
            concurrent.futures.wait(futures)
            op_results = [f.result() for f in futures]

        # --- assertions ---
        assert len(op_results) == 20
        # The registry should still be internally consistent
        for name in baseline_names:
            assert name in _registry, f"Baseline gate {name!r} disappeared"
        for name in _SAFE_NAMES[5:]:
            if name in _registry:
                cls = _registry.get(name)
                assert cls._gate_name == name  # type: ignore[attr-defined]
