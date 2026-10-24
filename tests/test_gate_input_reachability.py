"""Gate skip reasons and input reachability (issue #285).

Two halves of the same honesty problem:

* a skipped gate must carry WHY it skipped, all the way into the report;
* the coverage audit must say which gates can never have their inputs
  produced, instead of presenting every declared gate as if it inspected
  something.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.pipelines.gate_engine import GateLogEntry
from automedia.pipelines.gate_report import render_gate_report
from automedia.pipelines.runner import _build_gates_log
from automedia.validation.coverage import coverage_audit
from automedia.validation.gate_inputs import (
    audit_input_reachability,
    declared_gate_inputs,
    input_reachability_note,
    produced_context_keys,
)

_SRC = Path(__file__).resolve().parent.parent / "src" / "automedia"


# --------------------------------------------------------------------------- #
# skip_reason travels from the gate result into the report
# --------------------------------------------------------------------------- #


def test_build_gates_log_preserves_a_skip_reason() -> None:
    entries = _build_gates_log(
        [
            {
                "gate": "V1",
                "passed": True,
                "status": "skipped",
                "reason": "entries not produced by this pipeline",
            }
        ]
    )

    assert entries[0].skip_reason == "entries not produced by this pipeline"


def test_build_gates_log_falls_back_to_detail() -> None:
    """Some gates explain a skip in ``detail`` instead of ``reason``."""
    entries = _build_gates_log(
        [{"gate": "G1", "passed": True, "status": "skipped", "detail": "no brand identity"}]
    )

    assert entries[0].skip_reason == "no brand identity"


def test_non_skipped_gates_carry_no_skip_reason() -> None:
    entries = _build_gates_log([{"gate": "G0", "passed": True, "reason": "irrelevant"}])

    assert entries[0].skip_reason is None


def test_report_row_and_markdown_show_the_skip_reason() -> None:
    report = render_gate_report(
        "/tmp/project",
        [GateLogEntry("V1", "skipped", 0.0, skip_reason="entries not produced")],
    )

    assert report["gates"][0]["skip_reason"] == "entries not produced"
    assert "entries not produced" in report["markdown"]


def test_report_row_skip_reason_defaults_to_none() -> None:
    report = render_gate_report("/tmp/project", [GateLogEntry("G0", "passed", 1.0)])

    assert report["gates"][0]["skip_reason"] is None


# --------------------------------------------------------------------------- #
# Static input reachability
# --------------------------------------------------------------------------- #


def test_declared_inputs_are_read_from_the_real_gates() -> None:
    requirements = declared_gate_inputs(_SRC / "gates")

    assert requirements["V0"].required_keys == ("lint_result",)
    assert requirements["V1"].required_keys == ("entries",)
    assert requirements["V2"].required_keys == ("transcription", "audio_path")


def test_produced_keys_are_read_from_the_real_pipeline() -> None:
    produced = produced_context_keys(_SRC)

    # Written by the media stage when TTS + ASR actually ran.
    assert {"audio_path", "transcription", "whisper_text", "srt_text"} <= produced
    # Never written anywhere: these are the structurally dead inputs.
    assert "lint_result" not in produced
    assert "entries" not in produced


def test_reachability_separates_the_three_buckets() -> None:
    reachability = audit_input_reachability(_SRC / "gates", _SRC, {"V1", "V2", "G0"})

    assert reachability.reachable_gates == ("V2",)
    assert reachability.unreachable_gates == ("V1",)
    assert reachability.unknown_gates == ("G0",)
    assert reachability.missing_keys == {"V1": ("entries",)}


def test_a_gate_with_no_declared_inputs_is_never_claimed_reachable() -> None:
    """Absence of a declaration is not evidence of reachability."""
    reachability = audit_input_reachability(_SRC / "gates", _SRC, {"G0", "G1"})

    assert reachability.reachable_gates == ()
    assert reachability.unknown_gates == ("G0", "G1")


def test_note_states_all_three_buckets() -> None:
    reachability = audit_input_reachability(_SRC / "gates", _SRC, {"V1", "V2", "G0"})
    note = input_reachability_note(reachability)

    assert "1 of the 2 gates that DECLARE required inputs" in note
    assert "1 gates declare no required inputs" in note
    assert "V1(entries)" in note


def test_note_is_clean_when_every_declared_input_is_produced() -> None:
    reachability = audit_input_reachability(_SRC / "gates", _SRC, {"V2"})

    assert "will always report skipped" not in input_reachability_note(reachability)


# --------------------------------------------------------------------------- #
# The fifth coverage dimension
# --------------------------------------------------------------------------- #


def test_coverage_audit_reports_input_reachability() -> None:
    result = coverage_audit()

    assert result["input_reachable_gates"] == ["V2", "V5", "V7"]
    assert result["input_unreachable_gates"] == ["V0", "V1", "V3", "V4", "V6"]
    assert result["input_missing_keys"]["V1"] == ["entries"]
    assert result["summary"]["gates_input_reachable"] == 3
    assert result["summary"]["gates_input_unreachable"] == 5


def test_input_reachability_does_not_disturb_the_existing_classes() -> None:
    """The fifth dimension ADDS information; it must not reclassify gates."""
    result = coverage_audit()

    assert result["unreachable_gates"] == ["G4", "G5"]
    # The committed scenario library covers most gates, so `missing` is a small
    # residual; what matters is that the fifth dimension did not move it.
    assert isinstance(result["missing_gates"], list)
    assert set(result["missing_gates"]).isdisjoint(result["unreachable_gates"])


def test_input_unreachable_and_execution_unreachable_are_disjoint_reports() -> None:
    result = coverage_audit()

    assert set(result["input_unreachable_gates"]) & set(result["unreachable_gates"]) == set()


@pytest.mark.parametrize("gate", ["V0", "V1", "V3", "V4", "V6"])
def test_each_input_less_gate_names_the_missing_key(gate: str) -> None:
    result = coverage_audit()

    assert result["input_missing_keys"][gate], gate
