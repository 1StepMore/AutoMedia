"""Evidence-backed coverage (gap T-01).

Coverage is defined as declared surface ∩ surfaces reached by a ``passed``
step in the NEWEST persisted suite run.  ``covered`` requires a real-confidence
proof; a mock run, an unconfigured scenario, a boundary probe, and a meta
scenario never count.  ``unproven`` holds referenced-but-unproven surfaces;
``missing`` holds declared-but-unreferenced (Absent) surfaces; a surface is
excluded from ``unproven`` only while a versioned boundary-only allowlist
(owner + reason + unexpired) covers it.

All fixtures are synthetic (Red Line 4).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from automedia.validation.coverage import coverage_audit
from automedia.validation.persist import persist_run, write_latest_pointer

_STANDARD = "tool.contract"

TOOL_SCENARIO = """\
name: {name}
description: Synthetic fixture scenario.
intent: Prove the fixture surface contract.
category: baseline
requires_env: []
steps:
  - name: call the tool
    kind: tool
    check: The tool answers.
    standard: {standard}
    tool: {tool}
    arguments: {{}}
    expect:
      success: true
"""

PROVES_SCENARIO = """\
name: {name}
description: Synthetic fixture proving a gate and a mode.
intent: Prove the evidence half consumes proves_gates/proves_modes.
category: pipeline
proves_gates: [{gates}]
proves_modes: [{modes}]
steps:
  - name: call the tool
    kind: tool
    check: The tool answers.
    standard: {standard}
    tool: health_check
    arguments: {{}}
    expect:
      success: true
"""

BOUNDARY_SCENARIO = """\
name: {name}
description: Synthetic boundary probe.
intent: Prove boundary probes are never evidence.
category: surface
error_boundary: true
steps:
  - name: probe the boundary
    kind: tool
    check: The probe expects an error.
    standard: {standard}
    tool: cancel_pipeline
    arguments: {{}}
    expect: {{}}
"""

_HEALTH_SCENARIO = TOOL_SCENARIO.format(
    name="health-fixture", tool="health_check", standard=_STANDARD
)


def _write_lib(tmp_path: Path, files: dict[str, str]) -> Path:
    lib = tmp_path / "scenarios"
    for filename, content in files.items():
        path = lib / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return lib


def _step(target: str, *, passed: bool = True) -> dict:
    return {
        "step_index": 1,
        "surface": "tool",
        "target": target,
        "passed": passed,
        "status": "passed" if passed else "failed",
    }


def _persist(
    tmp_path: Path,
    scenarios: list[dict],
    *,
    confidence: str = "real",
    stamp: str = "20260101-000000-000000",
) -> Path:
    runs_root = tmp_path / "runs"
    persist_run(
        runs_root,
        {
            "trace_id": "trace-fixture",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "confidence": confidence,
            "scenarios": scenarios,
        },
        stamp=stamp,
    )
    write_latest_pointer(runs_root, stamp)
    return runs_root


def _allowlist(tmp_path: Path, entries: list[dict], *, version: int = 1) -> Path:
    lines = [f"version: {version}", 'reviewed: "2026-01-01"', "entries:"]
    for entry in entries:
        lines.append(f"  - surface: {entry['surface']}")
        lines.append(f"    name: {entry['name']}")
        lines.append(f"    owner: {entry['owner']}")
        lines.append(f"    reason: {entry['reason']}")
        if "expires" in entry:
            lines.append(f'    expires: "{entry["expires"]}"')
    path = tmp_path / "allowlist.yml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestNoEvidence:
    def test_no_runs_root_yields_empty_evidence(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {"health.yaml": _HEALTH_SCENARIO},
        )
        audit = coverage_audit(lib)
        assert audit["evidence_run"] is None
        assert audit["covered"]["mcp"] == []
        assert "health_check" in audit["unproven"]["mcp"]


class TestRealProof:
    def test_passed_step_marks_surface_covered(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {"health.yaml": _HEALTH_SCENARIO},
        )
        runs = _persist(
            tmp_path,
            [
                {
                    "scenario": "health-fixture",
                    "status": "passed",
                    "confidence": "real",
                    "error_boundary": False,
                    "steps": [_step("health_check")],
                }
            ],
        )
        audit = coverage_audit(lib, runs_root=runs)
        assert audit["evidence_run"] is not None
        assert audit["evidence_confidence"] == "real"
        assert "health_check" in audit["covered"]["mcp"]
        assert "health_check" not in audit["unproven"]["mcp"]

    def test_passed_scenario_marks_gates_and_modes_covered(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "health.yaml": _HEALTH_SCENARIO,
                "proves.yaml": PROVES_SCENARIO.format(
                    name="proves-fixture", gates="G0", modes="text_only", standard=_STANDARD
                ),
            },
        )
        runs = _persist(
            tmp_path,
            [
                {
                    "scenario": "proves-fixture",
                    "status": "passed",
                    "confidence": "real",
                    "error_boundary": False,
                    "steps": [_step("health_check")],
                }
            ],
        )
        audit = coverage_audit(lib, runs_root=runs)
        assert "G0" in audit["covered"]["gates"]
        assert "text_only" in audit["covered"]["modes"]

    def test_failed_step_is_not_covered(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {"health.yaml": _HEALTH_SCENARIO},
        )
        runs = _persist(
            tmp_path,
            [
                {
                    "scenario": "health-fixture",
                    "status": "failed",
                    "confidence": "real",
                    "error_boundary": False,
                    "steps": [_step("health_check", passed=False)],
                }
            ],
        )
        audit = coverage_audit(lib, runs_root=runs)
        assert "health_check" not in audit["covered"]["mcp"]
        assert "health_check" in audit["unproven"]["mcp"]


class TestMockAndBoundaryAndMetaNeverCount:
    def test_mock_run_leaves_surface_unproven(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {"health.yaml": _HEALTH_SCENARIO},
        )
        runs = _persist(
            tmp_path,
            [
                {
                    "scenario": "health-fixture",
                    "status": "passed",
                    "confidence": "mock",
                    "error_boundary": False,
                    "steps": [_step("health_check")],
                }
            ],
            confidence="mock",
        )
        audit = coverage_audit(lib, runs_root=runs)
        assert audit["evidence_confidence"] == "mock"
        assert "health_check" not in audit["covered"]["mcp"]
        assert "health_check" in audit["unproven"]["mcp"]

    def test_boundary_step_never_covered(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "boundary.yaml": BOUNDARY_SCENARIO.format(
                    name="cancel-boundary", standard=_STANDARD
                )
            },
        )
        runs = _persist(
            tmp_path,
            [
                {
                    "scenario": "cancel-boundary",
                    "status": "passed",
                    "confidence": "real",
                    "error_boundary": True,
                    "steps": [_step("cancel_pipeline")],
                }
            ],
        )
        audit = coverage_audit(lib, runs_root=runs)
        assert "cancel_pipeline" not in audit["covered"]["mcp"]

    def test_meta_scenario_never_covered(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "meta/self.yaml": TOOL_SCENARIO.format(
                    name="validation-self-check", tool="health_check", standard=_STANDARD
                )
            },
        )
        runs = _persist(
            tmp_path,
            [
                {
                    "scenario": "validation-self-check",
                    "status": "passed",
                    "confidence": "real",
                    "error_boundary": False,
                    "steps": [_step("health_check")],
                }
            ],
        )
        audit = coverage_audit(lib, runs_root=runs)
        assert "health_check" not in audit["covered"]["mcp"]


class TestAllowlist:
    def test_active_entry_excluded_from_unproven(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "boundary.yaml": BOUNDARY_SCENARIO.format(
                    name="cancel-boundary", standard=_STANDARD
                )
            },
        )
        runs = _persist(tmp_path, [], stamp="20260101-000001-000000")
        allow = _allowlist(
            tmp_path,
            [
                {
                    "surface": "mcp",
                    "name": "cancel_pipeline",
                    "owner": "validation-maintainer",
                    "reason": "positive path lands in T-05",
                    "expires": "2099-12-31",
                }
            ],
        )
        audit = coverage_audit(lib, runs_root=runs, allowlist_path=allow, today=date(2026, 9, 13))
        assert "cancel_pipeline" in audit["allowlisted"]["mcp"]
        assert "cancel_pipeline" not in audit["unproven"]["mcp"]

    def test_expired_entry_is_unproven_again(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {
                "boundary.yaml": BOUNDARY_SCENARIO.format(
                    name="cancel-boundary", standard=_STANDARD
                )
            },
        )
        runs = _persist(tmp_path, [], stamp="20260101-000001-000000")
        allow = _allowlist(
            tmp_path,
            [
                {
                    "surface": "mcp",
                    "name": "cancel_pipeline",
                    "owner": "validation-maintainer",
                    "reason": "expired",
                    "expires": "2020-01-01",
                }
            ],
        )
        audit = coverage_audit(lib, runs_root=runs, allowlist_path=allow, today=date(2026, 9, 13))
        assert audit["allowlisted"]["mcp"] == []
        assert "cancel_pipeline" in audit["unproven"]["mcp"]


class TestMissingBucket:
    def test_unreferenced_declared_surface_is_missing(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {"health.yaml": _HEALTH_SCENARIO},
        )
        audit = coverage_audit(lib)
        assert "pool_add_topic" in audit["missing"]["mcp"]
        assert "health_check" not in audit["missing"]["mcp"]

    def test_missing_count_serializes(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {"health.yaml": _HEALTH_SCENARIO},
        )
        audit = coverage_audit(lib)
        assert audit["missing_count"] > 0
        json.dumps(audit)
