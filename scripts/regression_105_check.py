#!/usr/bin/env python3
"""Regression check for issue #105: an H0 pause is resolvable and bounded.

Before this change a non-interactive ``automedia run`` blocked at the H0 gate for
a hardcoded 24 hours and then silently auto-approved, because the only approval
channel was the in-process ``_hitl_waiters`` registry and the engine passed
``project_dir=""``, leaving the ``.hitl_state.json`` branch unreachable.

Every assertion here is bounded and hermetic: the cross-process checks run
against a real ``automedia hitl approve`` subprocess and a real waiting
``PipelineProgress`` with a short timeout, so this check can never hang CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from automedia.hooks.pipeline_history import PipelineHistoryHook  # noqa: E402
from automedia.pipelines.gate_engine import GateEngine  # noqa: E402
from automedia.pipelines.gate_types import PipelineProgress  # noqa: E402

_MARKER = "REG105_HITL_DELIVERY_OK"
_FAILURES: list[str] = []
_WAIT_BUDGET_S = 20.0
_DELIVERY_GRACE_S = 10.0
_STUB_TIMEOUT_S = 15.0
# Deterministic (gitignored) so the scenario's own steps can address the very
# project the helper seeded, letting `automedia hitl pending|approve|reject`
# be exercised as real CLI leaves rather than hidden inside a helper.
_FIXTURE_ROOT = _REPO_ROOT / "validation-runs" / "regression-105-fixture"
_FIXTURE_APPROVE = "reg105ok"
_FIXTURE_REJECT = "reg105no"


def check(condition: bool, description: str) -> None:
    if not condition:
        _FAILURES.append(description)


def _seed_parked_project(root: Path, project_id: str) -> Path:
    project_dir = root / f"20260927_{project_id}"
    (project_dir / ".automedia").mkdir(parents=True)
    (project_dir / "00_project_info.json").write_text(
        json.dumps({"project_id": project_id, "topic": "reg105", "status": "draft"}),
        encoding="utf-8",
    )
    hook = PipelineHistoryHook()
    ctx = {"project_dir": str(project_dir), "project_id": project_id}
    hook.before_gate("G6", ctx)
    hook.after_gate("G6", ctx, {"passed": True})
    hook.before_gate("H0", ctx)
    return project_dir


# `automedia.cli.app` has no __main__ entry, so `-m` silently does nothing.
# Importing the Typer app directly is the one invocation that always works and
# does not depend on the console script being on PATH.
_CLI_BOOTSTRAP = "from automedia.cli.app import app; app()"


def _cli(*args: str, base_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", _CLI_BOOTSTRAP, *args, "--base-dir", str(base_dir)],
        capture_output=True,
        text=True,
        timeout=_WAIT_BUDGET_S,
        cwd=_REPO_ROOT,
        check=False,
    )


def _cli_help(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — argv is literals from this file
        [sys.executable, "-c", _CLI_BOOTSTRAP, *args, "--help"],
        capture_output=True,
        text=True,
        timeout=_WAIT_BUDGET_S,
        cwd=_REPO_ROOT,
        check=False,
    )


def check_bounded_timeout() -> None:
    """The pause budget is one hour, not the old hardcoded 24 hours."""
    from automedia.gates.h0_human_review import H0HumanReviewGate

    result = H0HumanReviewGate().execute({"skip_review": False, "hitl_config": {}})
    check(result["timeout_s"] == 3600, f"default timeout is {result['timeout_s']}, expected 3600")
    check(
        result["on_timeout"] == "reject",
        f"default on_timeout is {result['on_timeout']!r}, expected 'reject'",
    )


def check_timeout_fails_closed() -> None:
    """An undecided pause rejects; it must not auto-approve."""
    progress = PipelineProgress(project_id="reg105-timeout")
    check(
        progress.wait_for_hitl(timeout=0.3, on_timeout="reject") is False,
        "a timed-out pause did not reject under on_timeout=reject",
    )


def check_cli_surface() -> None:
    """The delivery subcommands exist on the shipped CLI."""
    proc = _cli_help("hitl")
    out = proc.stdout + proc.stderr
    for name in ("pending", "approve", "reject"):
        check(name in out, f"`automedia hitl {name}` is missing from --help")


class _PausingGate:
    """Stub gate that pauses like H0.

    Duck-typed, not a ``BaseGate`` subclass: subclassing auto-registers in the
    global ``GateRegistry`` singleton, which would leak into other checks.
    """

    gate_name = "H0"
    failure_mode = "stop"

    def __init__(self) -> None:
        self.timeout_s = _STUB_TIMEOUT_S
        self.on_timeout = "approve"

    def execute(self, gate_context: dict) -> dict:
        return {
            "passed": True,
            "gate": self.gate_name,
            "status": "awaiting_hitl",
            "timeout_s": self.timeout_s,
            "on_timeout": self.on_timeout,
        }


def _run_paused_gate(project_dir: Path, project_id: str) -> tuple[bool, bool, float]:
    """Run one gate that pauses, and report (ok, approved, elapsed).

    This goes through ``GateEngine`` on purpose.  Calling
    ``PipelineProgress.wait_for_hitl`` directly would pass even with the old
    ``project_dir=""`` wiring, because the bug was in the *engine*, not in the
    wait — so the check has to exercise the engine to have teeth.
    """
    engine = GateEngine(gates=[_PausingGate()])
    progress = PipelineProgress(project_id=project_id)
    context: dict = {"project_dir": str(project_dir), "topic": "reg105", "brand": "b"}
    start = time.monotonic()
    ok, results = engine.run(context, progress=progress)
    return ok, bool(results[0].get("_hitl_approved")), time.monotonic() - start


def check_cross_process_approval() -> None:
    """A real separate-process approval reaches a run paused inside the engine."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project_dir = _seed_parked_project(root, "reg105a")

        listed = _cli("hitl", "pending", base_dir=root)
        check(listed.returncode == 0, f"hitl pending failed: {listed.stderr[:200]}")
        check("reg105a" in listed.stdout, "hitl pending did not list the parked project")

        approved = _cli("hitl", "approve", "reg105a", base_dir=root)
        check(approved.returncode == 0, f"hitl approve failed: {approved.stderr[:200]}")

        ok, approved_gate, elapsed = _run_paused_gate(project_dir, "reg105a")
        check(ok is True, "the pipeline did not continue after the delivered approval")
        check(approved_gate is True, "the delivered approval was not honoured")
        check(
            elapsed < _STUB_TIMEOUT_S,
            f"the pause took {elapsed:.1f}s, so it ended by timeout rather than delivery",
        )
        check(
            not (project_dir / ".hitl_state.json").exists(),
            "the decision file was not consumed (it would leak into a later run)",
        )


def check_cross_process_rejection() -> None:
    """A real separate-process rejection halts a run paused inside the engine."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project_dir = _seed_parked_project(root, "reg105r")

        rejected = _cli("hitl", "reject", "reg105r", base_dir=root)
        check(rejected.returncode == 0, f"hitl reject failed: {rejected.stderr[:200]}")

        ok, approved_gate, elapsed = _run_paused_gate(project_dir, "reg105r")
        check(ok is False, "the pipeline continued after a delivered rejection")
        check(approved_gate is False, "the delivered rejection was not honoured")
        check(
            elapsed < _STUB_TIMEOUT_S,
            f"the pause took {elapsed:.1f}s, so it ended by timeout rather than delivery",
        )


def check_refuses_when_not_parked() -> None:
    """A decision cannot be planted for a run that is not waiting."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project_dir = root / "20260927_idle"
        (project_dir / ".automedia").mkdir(parents=True)
        (project_dir / "00_project_info.json").write_text(
            json.dumps({"project_id": "idle105", "topic": "t", "status": "draft"}),
            encoding="utf-8",
        )
        proc = _cli("hitl", "approve", "idle105", base_dir=root)
        check(proc.returncode != 0, "hitl approve succeeded for a project that is not parked")
        check(
            not (project_dir / ".hitl_state.json").exists(),
            "hitl approve planted a decision file for a project that is not parked",
        )


def check_stale_decision_cleared_at_run_start() -> None:
    """A leftover decision cannot auto-approve a later run."""
    from automedia.pipelines.runner import clear_stale_hitl_state

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stale = root / ".hitl_state.json"
        stale.write_text(json.dumps({"decision": "approve"}), encoding="utf-8")
        clear_stale_hitl_state(str(root))
        check(not stale.exists(), "a stale decision file survived run start")


def check_run_flags_exist() -> None:
    """The interactive and timeout knobs are on the shipped run command."""
    proc = _cli_help("run")
    out = proc.stdout + proc.stderr
    for flag in ("--wait-for-review", "--hitl-timeout", "--hitl-on-timeout"):
        check(flag in out, f"`automedia run {flag}` is missing from --help")


def seed_fixtures() -> None:
    """Create two parked projects the scenario's own steps can act on."""
    import shutil

    if _FIXTURE_ROOT.exists():
        shutil.rmtree(_FIXTURE_ROOT)
    _FIXTURE_ROOT.mkdir(parents=True)
    _seed_parked_project(_FIXTURE_ROOT, _FIXTURE_APPROVE)
    _seed_parked_project(_FIXTURE_ROOT, _FIXTURE_REJECT)


def consume_fixture(project_id: str) -> None:
    """Drive the engine against a seeded project and assert delivery worked."""
    project_dir = _FIXTURE_ROOT / f"20260927_{project_id}"
    ok, approved, elapsed = _run_paused_gate(project_dir, project_id)
    if not approved:
        _FAILURES.append(f"{project_id}: the delivered decision was not honoured")
    if elapsed >= _STUB_TIMEOUT_S:
        _FAILURES.append(f"{project_id}: the pause ended by timeout, not by delivery")
    if (project_dir / ".hitl_state.json").exists():
        _FAILURES.append(f"{project_id}: the decision file was not consumed")
    if project_id == _FIXTURE_APPROVE and not ok:
        _FAILURES.append("reg105ok: the pipeline did not continue after approval")
    if project_id == _FIXTURE_REJECT and ok:
        _FAILURES.append("reg105no: the pipeline continued after a rejection")


def main() -> int:
    args = set(sys.argv[1:])
    if "--seed" in args:
        seed_fixtures()
        print(f"REG105_FIXTURES_SEEDED {_FIXTURE_ROOT}")
        return 0
    if "--consume" in args:
        for project_id in sorted({a.split("=", 1)[1] for a in args if a.startswith("--consume=")}):
            consume_fixture(project_id)
        if _FAILURES:
            for failure in _FAILURES:
                print(f"REG105_FAIL: {failure}")
            return 1
        print(_MARKER)
        return 0

    for step in (
        check_bounded_timeout,
        check_timeout_fails_closed,
        check_cli_surface,
        check_run_flags_exist,
        check_cross_process_approval,
        check_cross_process_rejection,
        check_refuses_when_not_parked,
        check_stale_decision_cleared_at_run_start,
        seed_fixtures,
    ):
        try:
            step()
        except Exception as exc:  # a crashing check is a failing check
            _FAILURES.append(f"{step.__name__} raised {type(exc).__name__}: {exc}")

    if _FAILURES:
        for failure in _FAILURES:
            print(f"REG105_FAIL: {failure}")
        return 1
    print(_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
