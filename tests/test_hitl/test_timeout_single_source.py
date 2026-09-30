"""Single-source guard for the HITL/H0 pause budget (issue #131).

The one-hour pause budget used to be restated as an independent literal in four
uncoordinated places: ``manifests/defaults.yaml``, the H0 gate module constant,
the ``wait_for_hitl`` signature default, and the ``GateEngine`` fallback.  Only
the YAML config value may be a restatement (YAML cannot import Python); every
Python site must derive from the single canonical constant so the fallbacks
cannot silently drift away from the config default.  ``HITL_DEFAULT_TIMEOUT_S``
in ``automedia.hitl.constants`` is that canonical owner.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import yaml

from automedia.gates import h0_human_review
from automedia.hitl.constants import HITL_DEFAULT_TIMEOUT_S
from automedia.pipelines.gate_engine import GateEngine
from automedia.pipelines.gate_types import PipelineProgress

_DEFAULTS_YAML = (
    Path(__file__).resolve().parents[2] / "src" / "automedia" / "manifests" / "defaults.yaml"
)


def _yaml_hitl_timeout_s() -> object:
    """Return the config-layer default the runtime falls back to."""
    data = yaml.safe_load(_DEFAULTS_YAML.read_text(encoding="utf-8"))
    return data["gate_engine"]["hitl_timeout_s"]


def test_canonical_constant_is_a_plain_int() -> None:
    """The canonical owner is an int, matching the H0 gate's schema."""
    assert isinstance(HITL_DEFAULT_TIMEOUT_S, int)
    assert not isinstance(HITL_DEFAULT_TIMEOUT_S, bool)


def test_yaml_config_default_agrees_with_canonical_constant() -> None:
    """The YAML restatement cannot be the only thing that drifts."""
    assert _yaml_hitl_timeout_s() == HITL_DEFAULT_TIMEOUT_S


def test_h0_gate_fallback_reuses_the_canonical_constant() -> None:
    """H0 must reference the owner, not carry a second literal."""
    assert h0_human_review._DEFAULT_HITL_TIMEOUT_S is HITL_DEFAULT_TIMEOUT_S


def test_wait_for_hitl_default_is_the_canonical_budget_as_float() -> None:
    """The signature default keeps its float type while deriving from the owner."""
    default = inspect.signature(PipelineProgress.wait_for_hitl).parameters["timeout"].default
    assert default == HITL_DEFAULT_TIMEOUT_S
    assert isinstance(default, float)


def test_gate_engine_fallback_forwards_the_canonical_budget() -> None:
    """When a gate omits ``timeout_s`` the engine must use the owner's value."""

    class _AwaitingGate:
        gate_name = "STUB"
        failure_mode = "stop"

        def execute(self, gate_context: Any) -> dict[str, Any]:
            return {"passed": True, "gate": self.gate_name, "status": "awaiting_hitl"}

    recorded: dict[str, float] = {}

    class _RecordingProgress(PipelineProgress):
        def wait_for_hitl(
            self,
            project_dir: str = "",
            timeout: float = 0.0,
            on_timeout: str = "approve",
        ) -> bool:
            recorded["timeout"] = timeout
            return True

    engine = GateEngine(gates=[_AwaitingGate()])
    progress = _RecordingProgress(project_id="p131")
    ok, _results = engine.run({"project_dir": "", "topic": "t", "brand": "b"}, progress=progress)

    assert ok is True
    assert recorded["timeout"] == HITL_DEFAULT_TIMEOUT_S
