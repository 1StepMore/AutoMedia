"""Tests for DetectorRegistry — the BaseRegistry-based singleton.

Mirrors the GateRegistry contract: singleton lifecycle, registration by
``_detector_name``, ``get``/``get_all``/``list``/``contains``/``clear``,
duplicate rejection in ``_validate``, and a soft warning (never a hard
failure) when a registered detector's ``_env_required`` var is unset.
"""

from __future__ import annotations

import pytest

from automedia.detectors import (
    BaseDetector,
    DetectorRegistry,
    DetectorResult,
    DeterministicTasteDetector,
    GPTZeroStyleApiDetector,
)


class TestDetectorRegistrySingleton:
    """DetectorRegistry is a singleton with BaseRegistry CRUD semantics."""

    def test_singleton_instance(self) -> None:
        """Every DetectorRegistry() call returns the same instance."""
        assert DetectorRegistry() is DetectorRegistry()

    def test_list_is_sorted_and_contains_builtins(self) -> None:
        """list() returns sorted names including both built-in detectors."""
        names = DetectorRegistry().list()
        assert names == sorted(names)
        assert names == ["deterministic_taste", "gptzero_style_api"]

    def test_get_returns_detector_class(self) -> None:
        """get() resolves a registered detector by name."""
        assert DetectorRegistry().get("deterministic_taste") is DeterministicTasteDetector

    def test_get_unknown_raises_keyerror(self) -> None:
        """get() raises KeyError with the available names for an unknown key."""
        with pytest.raises(KeyError, match="no_such_detector"):
            DetectorRegistry().get("no_such_detector")

    def test_contains(self) -> None:
        """'in' works on the registry."""
        assert "deterministic_taste" in DetectorRegistry()
        assert "no_such_detector" not in DetectorRegistry()

    def test_get_all_returns_copy(self) -> None:
        """get_all() returns a detached copy of the name→class mapping."""
        mapping = DetectorRegistry().get_all()
        assert mapping["deterministic_taste"] is DeterministicTasteDetector
        mapping["deterministic_taste"] = None  # mutating the copy must not leak
        assert DetectorRegistry().get("deterministic_taste") is DeterministicTasteDetector


class TestDetectorRegistryValidation:
    """_validate rejects duplicates and warns (never fails) on missing env."""

    def test_duplicate_registration_rejected(self) -> None:
        """Registering an already-registered detector raises KeyError."""
        with pytest.raises(KeyError, match="deterministic_taste"):
            DetectorRegistry().register(DeterministicTasteDetector)

    def test_warns_when_env_required_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Registering an env-gated detector with its env var unset warns.

        The warning is a soft signal, not a hard failure — the detector is
        still registered (availability is a runtime question, not a
        registration question).
        """
        monkeypatch.delenv("AUTOMEDIA_DUMMY_DETECTOR_KEY", raising=False)
        try:
            with pytest.warns(UserWarning, match="AUTOMEDIA_DUMMY_DETECTOR_KEY"):

                class DummyEnvDetector(BaseDetector):
                    _detector_name = "dummy_env_detector"
                    _env_required = "AUTOMEDIA_DUMMY_DETECTOR_KEY"

                    def detect(self, text: str) -> DetectorResult:
                        return {
                            "name": "dummy_env_detector",
                            "ai_score": 0.0,
                            "passed": True,
                            "detail": "dummy",
                        }

            # The warning did not block registration.
            assert "dummy_env_detector" in DetectorRegistry()
            assert DetectorRegistry().get("dummy_env_detector") is DummyEnvDetector
        finally:
            # Clean up so the dummy does not pollute later tests.
            DetectorRegistry()._registry.pop("dummy_env_detector", None)


class TestDetectorRegistryClear:
    """clear() supports test isolation and allows re-registration."""

    def test_clear_removes_all_and_re_register_works(self) -> None:
        """After clear(), the registry is empty and re-registration succeeds."""
        registry = DetectorRegistry()
        registry.clear()
        try:
            assert len(registry) == 0
            assert "deterministic_taste" not in registry
            registry.register(DeterministicTasteDetector)
            registry.register(GPTZeroStyleApiDetector)
            assert len(registry) == 2
            assert "deterministic_taste" in registry
        finally:
            # Restore the full registry for the rest of the suite.
            registry.clear()
            registry.register(DeterministicTasteDetector)
            registry.register(GPTZeroStyleApiDetector)
