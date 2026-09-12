"""Expect evaluation and verdict aggregation for agent-tester scenarios (W1-T6).

Pure module: no subprocess, no network — artifact checks are ``os.path``
reads only.  Step *execution* belongs to the engine (W1-T7); this module
grades an already-produced ``output`` envelope against an :class:`Expect`
block and derives scenario verdicts.

Output envelope contract (produced by the adapters, W1-T4)::

    {"success": bool, "data": dict, "exit_code": int,
     "stdout": str, "stderr": str}

Conjoined semantics (guide §2.3): every assertion present in the block must
hold; absent fields are not evaluated.  An expect block with no present
assertions passes trivially at the evaluator level, but the loader rejects an
empty block on any non-boundary step (T-02) — a zero-assertion step can never
reach execution as evidence.  All failures are collected — never
short-circuited — and every failure names the failing expect key plus the
actual value observed (guide §4.7).

Check-type binding (T-02): :data:`CHECK_TYPE_EVALUATORS` binds every standard
check type in ``scenarios/STANDARDS.md`` to the expect-key evaluators that
grade it.  :data:`IMPLEMENTED_CHECK_TYPES` is the resulting closed set; the
standards registry rejects at load any handbook row whose check type is not in
it (``standards.py`` + ``loader.py``).  ``quality_spot_check`` is graded by the
explicit ``min_score`` / ``score_state`` assertions, never free text.

``gate_records_pass`` exact semantics (declared ``true`` in scenarios):

1. Resolve the artifact path in this order — first hit wins:
   (a) the ``artifact_exists`` path of the SAME expect block;
   (b) ``step.command`` when ``step.kind == "file"`` (the file-kind call
       spec carries the artifact path);
   (c) the first ``step.collect_artifacts`` entry's ``path``.
   With no resolvable path the assertion fails.
2. The path resolves against ``cwd`` (absolute paths are used as-is).
3. The file must exist and parse as JSON.
4. The parsed value must be a JSON object carrying gate/pass records: the
   first present of the keys ``"gates"``, ``"gate_results"``,
   ``"passed_gates"`` must be a NON-EMPTY list.
5. Every entry of that list must pass (T-03): an explicit
   ``passed: false`` or a ``status``/``result``/``state``/``outcome`` that
   is not a pass value fails the observation and names the offending entry.
   An entry with no pass indicator counts as a recorded pass.
6. A bare top-level ``"status"`` is NOT accepted — the minimal-pass fallback
   is removed; with no gate list the assertion fails.

The observed boolean is compared against the declared ``gate_records_pass``
value (``true`` in scenarios; declaring ``false`` inverts the check).

Verdict logic (guide §2.6/§2.7/§3.3): :func:`aggregate_status` implements
all-or-nothing (default), ``min_passing``, and ``pass_ratio`` policies and
the ``recovered`` upgrade; :func:`apply_recovery` implements recovery
verdicts — recovery NEVER erases RED, it only downgrades the verdict.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from automedia.validation.schema import Expect, Scenario, Step

_GATE_RECORD_KEYS: tuple[str, ...] = ("gates", "gate_results", "passed_gates")
"""Accepted key names for gate/pass record lists in a project-info JSON."""

_GATE_PASS_STATES: frozenset[str] = frozenset(
    {"passed", "pass", "success", "succeeded", "complete", "completed", "ok"}
)
"""Explicit pass values for a gate entry's status/result/state field (T-03)."""

_GATE_ENTRY_STATUS_KEYS: tuple[str, ...] = ("status", "result", "state", "outcome")
"""Gate-entry keys carrying an explicit pass/fail status (T-03)."""

_GATE_ENTRY_NAME_KEYS: tuple[str, ...] = ("name", "gate", "gate_name", "id")
"""Gate-entry keys naming the gate, for failure messages (T-03)."""

_SCORE_KEYS: tuple[str, ...] = ("quality_score", "overall_score", "score")
"""Output keys carrying a numeric quality score (T-02 quality_spot_check)."""

_STATE_KEYS: tuple[str, ...] = ("quality_state", "state")
"""Output keys carrying an explicit machine state (T-02 quality_spot_check)."""


@dataclass(frozen=True, slots=True)
class CheckTypeEvaluator:
    """Binding of one standard check type to the expect-key evaluators that
    grade it (T-02).  ``expect_keys`` is the canonical set of expect keys a
    step can use to exercise this check type; an empty tuple marks a
    status-scoped evaluator (for example the env gate behind ``unconfigured``).
    """

    check_type: str
    expect_keys: tuple[str, ...]


CHECK_TYPE_EVALUATORS: dict[str, CheckTypeEvaluator] = {
    "artifact_exists": CheckTypeEvaluator("artifact_exists", ("artifact_exists",)),
    "non_empty": CheckTypeEvaluator("non_empty", ("artifact_nonempty", "output_has", "stdout_has")),
    "gate_records_pass": CheckTypeEvaluator("gate_records_pass", ("gate_records_pass",)),
    "quality_spot_check": CheckTypeEvaluator("quality_spot_check", ("min_score", "score_state")),
    "data_has": CheckTypeEvaluator("data_has", ("data_has",)),
    "exit_code": CheckTypeEvaluator("exit_code", ("exit_code",)),
    "stdout": CheckTypeEvaluator("stdout", ("stdout_has",)),
    "stderr": CheckTypeEvaluator("stderr", ("stderr_has",)),
    "unconfigured": CheckTypeEvaluator("unconfigured", ()),
}
"""Every standard check type the framework can grade, bound to its evaluator keys."""

IMPLEMENTED_CHECK_TYPES: frozenset[str] = frozenset(CHECK_TYPE_EVALUATORS)
"""The closed set of check types with a registered evaluator (T-02)."""


@dataclass(frozen=True, slots=True)
class ExpectResult:
    """Verdict of one expect evaluation.

    ``failures`` lists one message per failing assertion; every message names
    the failing expect key (``expect.<key>``) and the observed value
    (guide §4.7).  ``passed`` is False iff ``failures`` is non-empty.
    """

    passed: bool
    failures: list[str]


class StepRecord(Protocol):
    """Structural contract for per-step records.

    The engine's (W1-T7) richer step trace satisfies this protocol when it
    carries ``passed: bool`` and ``status: str`` (statuses the aggregator
    understands: ``passed``, ``failed``, ``recovered``).  Plain ``bool``
    entries are also accepted by :func:`aggregate_status`.
    """

    @property
    def passed(self) -> bool: ...

    @property
    def status(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SimpleRecord:
    """Minimal concrete :class:`StepRecord` for tests and engine use."""

    passed: bool
    status: str


def evaluate_expect(
    expect: Expect,
    output: dict[str, object],
    *,
    step: Step | None = None,
    cwd: Path | None = None,
) -> ExpectResult:
    """Evaluate a conjoined expect block against an adapter output envelope.

    :param expect: the assertions to grade (absent fields are not evaluated).
    :param output: envelope with the adapter-produced ``success``/``data``/
        ``exit_code``/``stdout``/``stderr`` values.
    :param step: the step that produced the output; only consulted for
        ``gate_records_pass`` artifact-path resolution (see module docstring).
    :param cwd: base for relative artifact paths (default ``Path.cwd()``).
    """
    base = cwd if cwd is not None else Path.cwd()
    failures: list[str] = []

    if expect.success is not None:
        observed = output.get("success")
        if observed != expect.success:
            failures.append(f"expect.success: expected {expect.success}, observed {observed!r}")

    if expect.data_has is not None:
        data = output.get("data")
        if not isinstance(data, dict):
            failures.append(
                f"expect.data_has: output.data is not a dict (observed {type(data).__name__})"
            )
        else:
            missing = [key for key in expect.data_has if key not in data]
            if missing:
                failures.append(
                    "expect.data_has: missing key(s) "
                    f"{_fmt(missing)}; observed data keys: {_fmt(sorted(data))}"
                )

    if expect.exit_code is not None:
        observed = output.get("exit_code")
        if observed != expect.exit_code:
            failures.append(f"expect.exit_code: expected {expect.exit_code}, observed {observed!r}")

    if expect.stdout_has is not None:
        stdout = output.get("stdout")
        if not isinstance(stdout, str):
            stdout = ""
        missing = [s for s in expect.stdout_has if s not in stdout]
        if missing:
            failures.append(
                "expect.stdout_has: missing substring(s) "
                f"{_fmt(missing)}; observed stdout: {stdout!r}"
            )

    if expect.stderr_has is not None:
        stderr = output.get("stderr")
        if not isinstance(stderr, str):
            stderr = ""
        missing = [s for s in expect.stderr_has if s not in stderr]
        if missing:
            failures.append(
                "expect.stderr_has: missing substring(s) "
                f"{_fmt(missing)}; observed stderr: {stderr!r}"
            )

    if expect.artifact_exists is not None:
        resolved = _resolve_path(expect.artifact_exists, base)
        if not os.path.isfile(resolved):
            failures.append(
                "expect.artifact_exists: path "
                f"{expect.artifact_exists!r} is not a file (resolved {resolved})"
            )

    if expect.artifact_size_min is not None:
        target = expect.artifact_exists
        if target is None:
            # schema forbids this; guard Expect built programmatically
            failures.append("expect.artifact_size_min: no artifact_exists path in block to measure")
        else:
            resolved = _resolve_path(target, base)
            if os.path.isfile(resolved):
                size = os.path.getsize(resolved)
                if size < expect.artifact_size_min:
                    failures.append(
                        f"expect.artifact_size_min: file {target!r} size {size} "
                        f"< min {expect.artifact_size_min}"
                    )
            else:
                failures.append(
                    f"expect.artifact_size_min: path {target!r} is not a file (resolved {resolved})"
                )

    if expect.artifact_nonempty is not None:
        resolved = _resolve_path(expect.artifact_nonempty, base)
        if not os.path.isfile(resolved):
            failures.append(
                "expect.artifact_nonempty: path "
                f"{expect.artifact_nonempty!r} is not a file (resolved {resolved})"
            )
        elif os.path.getsize(resolved) == 0:
            failures.append(
                f"expect.artifact_nonempty: file {expect.artifact_nonempty!r} is empty (size 0)"
            )

    if expect.gate_records_pass is not None:
        observed, observation = _gate_records_observation(expect, step, base)
        if observed != expect.gate_records_pass:
            failures.append(
                "expect.gate_records_pass: expected "
                f"{expect.gate_records_pass}, observed {observation}"
            )

    if expect.output_has is not None:
        observed_keys = sorted(output) if isinstance(output, dict) else []
        missing = [key for key in expect.output_has if key not in observed_keys]
        if missing:
            failures.append(
                "expect.output_has: missing key(s) "
                f"{_fmt(missing)}; observed keys: {_fmt(observed_keys)}"
            )

    if expect.min_score is not None:
        score = _observed_score(output)
        if score is None:
            failures.append(
                "expect.min_score: no numeric quality score in output; observed "
                f"keys: {_fmt(sorted(output) if isinstance(output, dict) else [])}"
            )
        elif score < expect.min_score:
            failures.append(f"expect.min_score: observed score {score} < min {expect.min_score}")

    if expect.score_state is not None:
        state = _observed_state(output)
        if state is None:
            failures.append(
                "expect.score_state: no machine state in output; observed keys: "
                f"{_fmt(sorted(output) if isinstance(output, dict) else [])}"
            )
        elif state not in expect.score_state:
            failures.append(
                f"expect.score_state: observed state {state!r} not in allowed "
                f"{_fmt(expect.score_state)}"
            )

    return ExpectResult(passed=not failures, failures=failures)


def aggregate_status(scenario: Scenario, step_results: Sequence[bool | StepRecord]) -> str:
    """Derive the scenario verdict from per-step results (guide §2.7/§3.3).

    Returns ``"passed"`` | ``"failed"`` | ``"partial-pass"`` | ``"recovered"``.

    - No failed steps: ``"recovered"`` if any step is recorded ``"recovered"``
      (recovery never erases RED — the run record still shows the failure),
      else ``"passed"``.
    - Some failed steps: ``"partial-pass"`` when the succeeded count meets
      ``scenario.min_passing`` (checked first) or
      ``passed / total >= scenario.pass_ratio``; absent both policies the
      default is all-or-nothing → ``"failed"``.
    - Recovered steps count as succeeded for partial-pass arithmetic
      (guide §3.3: a recovered record carries ``passed=True``).

    ``step_results`` accepts plain ``bool`` entries (``True`` = passed,
    ``False`` = failed) or any object satisfying :class:`StepRecord`.
    """
    records = [
        SimpleRecord(passed=r, status="passed" if r else "failed") if isinstance(r, bool) else r
        for r in step_results
    ]
    failed = [r for r in records if not r.passed]
    if not failed:
        return "recovered" if any(r.status == "recovered" for r in records) else "passed"
    passed = len(records) - len(failed)
    if scenario.min_passing is not None:
        return "partial-pass" if passed >= scenario.min_passing else "failed"
    if scenario.pass_ratio is not None and records:
        return "partial-pass" if passed / len(records) >= scenario.pass_ratio else "failed"
    return "failed"


def should_run_recovery(primary: StepRecord) -> bool:
    """True when the primary step failed and its recovery steps should run.

    The engine calls this after the primary expect evaluation; a primary
    that passed never runs recovery (guide §2.6).
    """
    return not primary.passed


def apply_recovery(primary_passed: bool, recovery_results: Sequence[bool]) -> str:
    """Derive the step verdict after recovery steps ran (guide §2.6/§4.6).

    - primary passed → ``"passed"`` (recovery never applies to a green step);
    - primary failed AND any recovery passed → ``"recovered"`` — the failure
      stays in the run record, only its effect on the verdict is downgraded;
    - primary failed AND no recovery passed (or none ran) → ``"failed"``.

    Recovery NEVER erases RED: the return value is never ``"passed"`` when the
    primary failed.
    """
    if primary_passed:
        return "passed"
    return "recovered" if any(recovery_results) else "failed"


# --- helpers ---------------------------------------------------------------


def _resolve_path(path: str, cwd: Path) -> Path:
    """Resolve ``path`` against ``cwd``; absolute paths are used as-is."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else cwd / candidate


def _gate_records_path(expect: Expect, step: Step | None) -> str | None:
    """Resolve the gate-records artifact path (module docstring order)."""
    if expect.artifact_exists:
        return expect.artifact_exists
    if step is not None and step.kind == "file" and step.command:
        return step.command
    if step is not None and step.collect_artifacts:
        return step.collect_artifacts[0].path
    return None


def _gate_records_observation(expect: Expect, step: Step | None, cwd: Path) -> tuple[bool, str]:
    """Inspect the gate-records artifact; return ``(observed, observation)``."""
    path = _gate_records_path(expect, step)
    if path is None:
        return (
            False,
            "no artifact path resolvable "
            "(no artifact_exists, step.command for kind=file, or collect_artifacts)",
        )
    resolved = _resolve_path(path, cwd)
    if not os.path.isfile(resolved):
        return False, f"artifact {path} does not exist (resolved {resolved})"
    try:
        with open(resolved, encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (OSError, json.JSONDecodeError) as err:
        return False, f"{path} not parseable as JSON: {err}"
    if not isinstance(parsed, dict):
        return False, f"{path} parsed as {type(parsed).__name__}, not a JSON object"
    for key in _GATE_RECORD_KEYS:
        if key not in parsed:
            continue
        value = parsed[key]
        if not isinstance(value, list):
            return False, f"{key}: {type(value).__name__}, not a list"
        if not value:
            return False, f"{key}: empty list"
        for index, entry in enumerate(value, 1):
            if _gate_entry_passed(entry) is False:
                return False, (
                    f"{key}: entry {index} ({_gate_entry_label(entry, index)}) did "
                    f"not pass; observed {entry!r}"
                )
        return True, f"{key}: {len(value)} record(s), all passed"
    return False, f"no gate records (keys: {sorted(parsed)})"


def _gate_entry_passed(entry: object) -> bool | None:
    """The pass/fail verdict of one gate entry (T-03).

    True/False when the entry carries an explicit pass indicator; None when
    it carries none (bare record presence, which counts as a recorded pass).
    """
    if isinstance(entry, bool):
        return entry
    if isinstance(entry, str):
        return True
    if not isinstance(entry, dict):
        return None
    if "passed" in entry:
        value = entry["passed"]
        return value if isinstance(value, bool) else None
    for key in _GATE_ENTRY_STATUS_KEYS:
        value = entry.get(key)
        if isinstance(value, str):
            return value.strip().lower() in _GATE_PASS_STATES
    return None


def _gate_entry_label(entry: object, index: int) -> str:
    """A human-readable label for a gate entry in failure messages."""
    if isinstance(entry, str) and entry:
        return entry
    if isinstance(entry, dict):
        for key in _GATE_ENTRY_NAME_KEYS:
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
    return f"#{index}"


def _fmt(items: Sequence[object]) -> str:
    """Join items as comma-separated reprs (failure messages name observed values)."""
    return ", ".join(repr(item) for item in items)


def _observed_score(output: object) -> float | None:
    """The first numeric quality score in the envelope (top level or ``data``)."""
    if not isinstance(output, dict):
        return None
    candidates = [output.get(key) for key in _SCORE_KEYS]
    data = output.get("data")
    if isinstance(data, dict):
        candidates.extend(data.get(key) for key in _SCORE_KEYS)
    for candidate in candidates:
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, (int, float)):
            return float(candidate)
    return None


def _observed_state(output: object) -> str | None:
    """The explicit machine state in the envelope (top level or ``data``)."""
    if not isinstance(output, dict):
        return None
    for key in _STATE_KEYS:
        value = output.get(key)
        if isinstance(value, str):
            return value
    data = output.get("data")
    if isinstance(data, dict):
        for key in _STATE_KEYS:
            value = data.get(key)
            if isinstance(value, str):
                return value
    return None
