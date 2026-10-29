"""Expect evaluation and verdict aggregation for agent-tester scenarios (W1-T6).

Pure module: no network — artifact checks are ``os.path`` reads plus the
read-only probes in :mod:`automedia.validation.media_probe` (image inspection
via Pillow, media inspection via an ``ffprobe`` subprocess).  Step *execution*
belongs to the engine (W1-T7); this module grades an already-produced
``output`` envelope against an :class:`Expect` block and derives scenario
verdicts.

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
from typing import Any, Protocol

from automedia.validation.media_probe import (
    glob_artifacts,
    is_image_path,
    probe_image,
    probe_media,
    probe_srt,
    probe_text,
)
from automedia.validation.schema import (
    Expect,
    MediaExpect,
    Scenario,
    Step,
)

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

_ERROR_CODE_KEYS: tuple[str, ...] = ("code", "error_code", "errorCode")
"""Error-dict keys carrying the machine-readable code (R-08)."""

_RECOVERY_KEYS: tuple[str, ...] = (
    "resolution",
    "recovery",
    "remediation",
    "guidance",
    "hint",
    "instruction",
)
"""Error-dict keys carrying the recovery instruction string (R-08)."""

_TRACE_ID_KEYS: tuple[str, ...] = ("trace_id", "traceId", "correlation_id", "correlationId")
"""Keys carrying a trace/correlation identifier (Tr-01)."""


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
    "media_structure": CheckTypeEvaluator(
        "media_structure", ("artifact_exists", "artifact_glob", "media")
    ),
    "text_structure": CheckTypeEvaluator("text_structure", ("artifact_exists", "text")),
    "subtitle_structure": CheckTypeEvaluator("subtitle_structure", ("artifact_exists", "subtitle")),
    "keyword_coverage": CheckTypeEvaluator(
        "keyword_coverage", ("artifact_exists", "keyword_coverage")
    ),
    "artifact.glob-exists": CheckTypeEvaluator("artifact.glob-exists", ("artifact_glob",)),
    "media.video": CheckTypeEvaluator("media.video", ("artifact_exists", "artifact_glob", "media")),
    "media.audio": CheckTypeEvaluator("media.audio", ("artifact_exists", "artifact_glob", "media")),
    "media.image": CheckTypeEvaluator("media.image", ("artifact_exists", "artifact_glob", "media")),
    "media.carousel": CheckTypeEvaluator("media.carousel", ("artifact_glob", "media")),
    "text.article": CheckTypeEvaluator("text.article", ("artifact_exists", "text")),
    "subtitle.srt": CheckTypeEvaluator("subtitle.srt", ("artifact_exists", "subtitle")),
    "quality.keyword-coverage": CheckTypeEvaluator(
        "quality.keyword-coverage", ("artifact_exists", "keyword_coverage")
    ),
    "text.similarity": CheckTypeEvaluator(
        "text.similarity", ("artifact_exists", "text_similarity")
    ),
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

    if expect.error_expected is not True:
        signal = _error_signal(output)
        if signal is not None:
            failures.append(
                f"expect.error_expected: call reported an error ({signal}); declare "
                "error_expected: true to opt in to an error-exercising step"
            )

    if expect.error_code_has is not None:
        code = _error_code(output)
        if code is None:
            failures.append(
                "expect.error_code_has: no non-empty error code in output; observed "
                f"keys: {_fmt(sorted(output) if isinstance(output, dict) else [])}"
            )
        else:
            missing = [substring for substring in expect.error_code_has if substring not in code]
            if missing:
                failures.append(
                    f"expect.error_code_has: code {code!r} missing substring(s) {_fmt(missing)}"
                )

    if expect.recovery_has is not None:
        recovery = _recovery_text(output)
        if recovery is None:
            failures.append(
                "expect.recovery_has: no non-empty recovery/resolution string in output; "
                f"observed keys: {_fmt(sorted(output) if isinstance(output, dict) else [])}"
            )
        else:
            missing = [substring for substring in expect.recovery_has if substring not in recovery]
            if missing:
                failures.append(
                    "expect.recovery_has: recovery "
                    f"{recovery!r} missing substring(s) {_fmt(missing)}"
                )

    if expect.trace_id is not None:
        failures.extend(_trace_id_failures(expect.trace_id, output))

    if expect.artifact_glob is not None and expect.media is None:
        failures.extend(_artifact_glob_failures(expect, step, base))

    if expect.media is not None:
        failures.extend(_media_failures(expect, step, base))

    if expect.text is not None:
        failures.extend(_text_failures(expect, step, base))

    if expect.subtitle is not None:
        failures.extend(_subtitle_failures(expect, step, base))

    if expect.keyword_coverage is not None:
        failures.extend(_keyword_coverage_failures(expect, step, base))

    if expect.text_similarity is not None:
        failures.extend(_text_similarity_failures(expect, step, base))

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


# --- Phase 1.1 media / text / subtitle / keyword grading -------------------


def _artifact_glob_root(step: Step | None, base: Path) -> Path:
    """Directory a relative ``artifact_glob`` pattern is matched under.

    For a ``file`` step the command is the artifact (or artifact directory);
    a directory command is the root, a file command contributes its parent.
    Without a usable command the engine's ``cwd`` is the root.
    """
    if step is not None and step.kind == "file" and step.command:
        candidate = _resolve_path(step.command, base)
        if candidate.is_dir():
            return candidate
        if candidate.exists() or candidate.suffix:
            return candidate.parent
    return base


def _artifact_glob_failures(expect: Expect, step: Step | None, base: Path) -> list[str]:
    """Standalone ``artifact.glob-exists``: the pattern must match >= 1 file."""
    if expect.artifact_glob is None:
        return []
    root = _artifact_glob_root(step, base)
    matches = glob_artifacts(str(root), expect.artifact_glob)
    if not matches:
        return [
            f"expect.artifact_glob: pattern {expect.artifact_glob!r} matched no files under {root}"
        ]
    return []


def _media_targets(expect: Expect, step: Step | None, base: Path) -> tuple[list[Path], list[str]]:
    """Resolve the media target set and any locator failures."""
    failures: list[str] = []
    if expect.artifact_glob is not None:
        root = _artifact_glob_root(step, base)
        matches = [Path(match) for match in glob_artifacts(str(root), expect.artifact_glob)]
        if not matches:
            failures.append(
                "expect.media: artifact_glob "
                f"{expect.artifact_glob!r} matched no files under {root}"
            )
        return matches, failures
    if expect.artifact_exists is not None:
        resolved = _resolve_path(expect.artifact_exists, base)
        if not resolved.is_file():
            failures.append(
                "expect.media: artifact_exists path "
                f"{expect.artifact_exists!r} is not a file (resolved {resolved})"
            )
            return [], failures
        return [resolved], failures
    failures.append("expect.media: no artifact_exists or artifact_glob path to inspect")
    return [], failures


def _media_failures(expect: Expect, step: Step | None, base: Path) -> list[str]:
    if expect.media is None:
        return []
    media = expect.media
    targets, failures = _media_targets(expect, step, base)
    if not targets:
        return failures
    if media.min_count is not None and len(targets) < media.min_count:
        failures.append(f"expect.media.min_count: observed {len(targets)} < min {media.min_count}")
    check_type = _standard_check_type(step)
    needs_image = any(
        value is not None
        for value in (media.min_width, media.min_height, media.non_uniform, media.same_size)
    )
    needs_media = check_type in {"media.video", "media.audio"} or any(
        value is not None
        for value in (
            media.min_duration_s,
            media.max_duration_s,
            media.min_bitrate_kbps,
            media.decodable,
            media.codec,
        )
    )
    if check_type in {"media.image", "media.carousel"}:
        image_targets, media_targets = targets, []
    elif check_type in {"media.video", "media.audio"}:
        image_targets, media_targets = [], targets
    elif needs_image and not needs_media:
        image_targets, media_targets = targets, []
    elif needs_media and not needs_image:
        image_targets, media_targets = [], targets
    else:
        image_targets = [path for path in targets if is_image_path(path)]
        media_targets = [path for path in targets if not is_image_path(path)]
    image_probes = [(path, probe_image(path)) for path in image_targets]
    media_probes = [(path, probe_media(path)) for path in media_targets]
    for path, probe in image_probes:
        if probe.get("ok") is not True:
            failures.append(f"expect.media: image probe failed for {path}: {probe.get('error')}")
    for path, probe in media_probes:
        if probe.get("ok") is not True:
            failures.append(f"expect.media: media probe failed for {path}: {probe.get('error')}")
    for path, probe in image_probes:
        if probe.get("ok") is not True:
            continue
        failures.extend(_image_criterion_failures(path, probe, media))
    for path, probe in media_probes:
        if probe.get("ok") is not True:
            continue
        failures.extend(_media_criterion_failures(path, probe, media, check_type))
    if media.same_size is not None:
        sizes = {
            (probe.get("width"), probe.get("height"))
            for _, probe in image_probes
            if probe.get("ok") is True
        }
        observed_same = len(sizes) == 1
        if media.same_size and not observed_same:
            failures.append(
                "expect.media.same_size: observed differing sizes "
                f"{sorted(str(size) for size in sizes)}"
            )
        if media.same_size is False and observed_same and sizes:
            failures.append(
                "expect.media.same_size: observed one uniform size "
                f"{sorted(str(size) for size in sizes)}"
            )
    return failures


def _image_criterion_failures(path: Path, probe: dict[str, Any], media: MediaExpect) -> list[str]:
    failures: list[str] = []
    width = probe.get("width")
    height = probe.get("height")
    if media.min_width is not None and (width is None or width < media.min_width):
        failures.append(
            f"expect.media.min_width: {path.name} observed {width} < min {media.min_width}"
        )
    if media.min_height is not None and (height is None or height < media.min_height):
        failures.append(
            f"expect.media.min_height: {path.name} observed {height} < min {media.min_height}"
        )
    observed_non_uniform = probe.get("non_uniform")
    if (
        media.non_uniform is not None
        and observed_non_uniform is not None
        and observed_non_uniform != media.non_uniform
    ):
        failures.append(
            f"expect.media.non_uniform: {path.name} observed {observed_non_uniform} "
            f"(expected {media.non_uniform}; stddev {probe.get('stddev')})"
        )
    return failures


def _media_criterion_failures(
    path: Path,
    probe: dict[str, Any],
    media: MediaExpect,
    check_type: str,
) -> list[str]:
    failures: list[str] = []
    duration = probe.get("duration_s")
    bitrate = probe.get("bitrate_kbps")
    if check_type == "media.video" and probe.get("has_video") is not True:
        failures.append(f"expect.media: {path.name} has no video stream")
    if check_type == "media.audio" and probe.get("has_audio") is not True:
        failures.append(f"expect.media: {path.name} has no audio stream")
    if media.min_duration_s is not None and (duration is None or duration < media.min_duration_s):
        failures.append(
            f"expect.media.min_duration_s: {path.name} observed {duration} "
            f"< min {media.min_duration_s}"
        )
    if media.max_duration_s is not None and (duration is None or duration > media.max_duration_s):
        failures.append(
            f"expect.media.max_duration_s: {path.name} observed {duration} "
            f"> max {media.max_duration_s}"
        )
    if media.min_bitrate_kbps is not None and (bitrate is None or bitrate < media.min_bitrate_kbps):
        failures.append(
            f"expect.media.min_bitrate_kbps: {path.name} observed {bitrate} "
            f"< min {media.min_bitrate_kbps}"
        )
    if media.decodable is not None:
        observed = probe.get("ok") is True and probe.get("decodable") is True
        if observed != media.decodable:
            failures.append(
                f"expect.media.decodable: {path.name} observed {observed} "
                f"(expected {media.decodable})"
            )
    if media.codec is not None:
        observed_codec = probe.get("codec")
        if not isinstance(observed_codec, str) or observed_codec.lower() != media.codec.lower():
            failures.append(
                f"expect.media.codec: {path.name} observed {observed_codec!r} "
                f"(expected {media.codec!r})"
            )
    if check_type != "media.audio":
        width = probe.get("width")
        height = probe.get("height")
        if media.min_width is not None and (width is None or width < media.min_width):
            failures.append(
                f"expect.media.min_width: {path.name} observed {width} < min {media.min_width}"
            )
        if media.min_height is not None and (height is None or height < media.min_height):
            failures.append(
                f"expect.media.min_height: {path.name} observed {height} < min {media.min_height}"
            )
    return failures


def _text_failures(expect: Expect, step: Step | None, base: Path) -> list[str]:
    text_expect = expect.text
    if text_expect is None:
        return []
    path = expect.artifact_exists
    if path is None and step is not None and step.kind == "file":
        path = step.command
    if path is None:
        return ["expect.text: no artifact_exists path or file-step command to inspect"]
    probe = probe_text(_resolve_path(path, base))
    if probe.get("ok") is False:
        return [f"expect.text: probe failed for {path}: {probe.get('error')}"]
    failures: list[str] = []
    if text_expect.min_paragraphs is not None:
        observed = probe["paragraphs"]
        if observed < text_expect.min_paragraphs:
            failures.append(
                f"expect.text.min_paragraphs: observed {observed} "
                f"< min {text_expect.min_paragraphs}"
            )
    if text_expect.min_chars is not None:
        observed = probe["chars"]
        if observed < text_expect.min_chars:
            failures.append(
                f"expect.text.min_chars: observed {observed} < min {text_expect.min_chars}"
            )
    if text_expect.min_headings is not None:
        observed = probe["headings"]
        if observed < text_expect.min_headings:
            failures.append(
                f"expect.text.min_headings: observed {observed} < min {text_expect.min_headings}"
            )
    if text_expect.has_heading is not None:
        observed = probe["has_heading"]
        if observed != text_expect.has_heading:
            failures.append(
                f"expect.text.has_heading: observed {observed} (expected {text_expect.has_heading})"
            )
    return failures


def _subtitle_failures(expect: Expect, step: Step | None, base: Path) -> list[str]:
    subtitle = expect.subtitle
    if subtitle is None:
        return []
    path = expect.artifact_exists
    if path is None and step is not None and step.kind == "file":
        path = step.command
    if path is None:
        return ["expect.subtitle: no artifact_exists path or file-step command to inspect"]
    probe = probe_srt(_resolve_path(path, base))
    if probe.get("ok") is False:
        return [f"expect.subtitle: probe failed for {path}: {probe.get('error')}"]
    failures: list[str] = []
    if subtitle.min_cues is not None and probe["cues"] < subtitle.min_cues:
        failures.append(
            f"expect.subtitle.min_cues: observed {probe['cues']} < min {subtitle.min_cues}"
        )
    if subtitle.monotonic is not None and probe["monotonic"] != subtitle.monotonic:
        failures.append(
            f"expect.subtitle.monotonic: observed {probe['monotonic']} "
            f"(expected {subtitle.monotonic})"
        )
    if subtitle.within is not None:
        media_probe = probe_media(_resolve_path(subtitle.within, base))
        duration = media_probe.get("duration_s")
        last_end = probe.get("last_end_s")
        if media_probe.get("ok") is False or duration is None:
            failures.append(
                "expect.subtitle.within: media "
                f"{subtitle.within!r} not decodable ({media_probe.get('error')})"
            )
        elif last_end is None or last_end > duration + 0.5:
            failures.append(
                f"expect.subtitle.within: last cue end {last_end} > media duration "
                f"{duration} + 0.5s tolerance"
            )
    return failures


def _keyword_coverage_failures(expect: Expect, step: Step | None, base: Path) -> list[str]:
    coverage = expect.keyword_coverage
    if coverage is None:
        return []
    paths = coverage.over
    if paths is None:
        if expect.artifact_exists is None:
            return ["expect.keyword_coverage: no artifact_exists path and no 'over' list"]
        paths = [expect.artifact_exists]
    if expect.artifact_glob is not None:
        read_base = _artifact_glob_root(step, base)
    elif step is not None and step.kind == "file" and step.command:
        command_path = _resolve_path(step.command, base)
        read_base = command_path if command_path.is_dir() else command_path.parent
    else:
        read_base = base
    chunks: list[str] = []
    failures: list[str] = []
    for raw in paths:
        resolved = _resolve_path(raw, read_base)
        try:
            chunks.append(resolved.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            failures.append(f"expect.keyword_coverage: cannot read {raw!r}: {exc}")
    if failures:
        return failures
    haystack = _normalize_text("\n".join(chunks))
    missing = [keyword for keyword in coverage.keywords if _normalize_text(keyword) not in haystack]
    total = len(coverage.keywords)
    hits = total - len(missing)
    ratio = hits / total if total else 0.0
    if ratio < coverage.min_ratio:
        failures.append(
            "expect.keyword_coverage: missing keyword(s) "
            f"{_fmt(missing)}; observed ratio {hits}/{total} = {ratio:.2f} "
            f"< min {coverage.min_ratio}"
        )
    return failures


_SUBTITLE_SUFFIXES = frozenset({".srt", ".vtt"})


def _comparable_text(path: Path) -> str:
    """Read a file for similarity; subtitles contribute dialogue lines only."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() not in _SUBTITLE_SUFFIXES:
        return text
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or "-->" in stripped
            or stripped.isdigit()
            or stripped.upper().startswith("WEBVTT")
        ):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _similarity_chars(text: str) -> str:
    """Keep letters/digits only: drops punctuation, markdown, and whitespace."""
    return "".join(char for char in text if char.isalnum()).lower()


def _bigrams(text: str) -> set[str]:
    """Character bigrams; a one-character text yields its single character."""
    normalized = _similarity_chars(text)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _dice_ratio(candidate: str, reference: str) -> float:
    """Dice coefficient over character bigrams (0.0-1.0)."""
    candidate_grams = _bigrams(candidate)
    reference_grams = _bigrams(reference)
    if not candidate_grams or not reference_grams:
        return 0.0
    overlap = len(candidate_grams & reference_grams)
    return 2 * overlap / (len(candidate_grams) + len(reference_grams))


def _text_similarity_failures(expect: Expect, step: Step | None, base: Path) -> list[str]:
    """Grade produced text against a reference by character-bigram similarity."""
    similarity = expect.text_similarity
    if similarity is None:
        return []
    paths = similarity.over
    if paths is None:
        if expect.artifact_exists is None:
            return ["expect.text_similarity: no artifact_exists path and no 'over' list"]
        paths = [expect.artifact_exists]
    if expect.artifact_glob is not None:
        read_base = _artifact_glob_root(step, base)
    elif step is not None and step.kind == "file" and step.command:
        command_path = _resolve_path(step.command, base)
        read_base = command_path if command_path.is_dir() else command_path.parent
    else:
        read_base = base
    chunks: list[str] = []
    failures: list[str] = []
    for raw in paths:
        resolved = _resolve_path(raw, read_base)
        try:
            chunks.append(_comparable_text(resolved))
        except OSError as exc:
            failures.append(f"expect.text_similarity: cannot read {raw!r}: {exc}")
    reference_path = _resolve_path(similarity.reference, base)
    try:
        reference = _comparable_text(reference_path)
    except OSError as exc:
        failures.append(
            f"expect.text_similarity: cannot read reference {similarity.reference!r}: {exc}"
        )
        return failures
    if failures:
        return failures
    ratio = _dice_ratio("\n".join(chunks), reference)
    if ratio < similarity.min_ratio:
        failures.append(
            "expect.text_similarity: observed ratio "
            f"{ratio:.2f} < min {similarity.min_ratio} against {similarity.reference!r}"
        )
    return failures


def _normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace, and fold full-width ASCII to half-width."""
    folded = "".join(
        chr(ord(char) - 0xFEE0) if 0xFF01 <= ord(char) <= 0xFF5E else char for char in text
    )
    return "".join(folded.split()).lower()


# --- helpers ---------------------------------------------------------------

_MEDIA_CHECK_TYPES = frozenset({"media.video", "media.audio", "media.image", "media.carousel"})


def _standard_check_type(step: Step | None) -> str:
    """The media check type declared by ``step.standard`` (handbook key == type)."""
    if step is None:
        return ""
    return step.standard if step.standard in _MEDIA_CHECK_TYPES else ""


def _resolve_path(path: str, cwd: Path) -> Path:
    """Resolve ``path`` against ``cwd``; absolute paths are used as-is."""
    candidate = Path(os.path.expandvars(path))
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


def _error_signal(output: object) -> str | None:
    """The error signal in an adapter envelope, or None when it reports success.

    A tool ``success: false`` envelope and a CLI nonzero ``exit_code`` are
    errors by default (T-04); ``expect.error_expected: true`` opts out.
    """
    if not isinstance(output, dict):
        return None
    if output.get("success") is False:
        return "success=false"
    exit_code = output.get("exit_code")
    if isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0:
        return f"exit_code={exit_code}"
    return None


def _error_object(output: object) -> dict[str, object] | None:
    """The structured ``error`` dict in an envelope (top level or under ``data``)."""
    if not isinstance(output, dict):
        return None
    error = output.get("error")
    if isinstance(error, dict):
        return error
    data = output.get("data")
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return error
    return None


def _error_code(output: object) -> str | None:
    """The non-empty machine-readable error code in an envelope, or None (R-08).

    Resolution order: the structured ``error`` dict's ``code``/``error_code``,
    then the same keys at the envelope top level, then a ``data`` nested
    envelope.  An empty or non-string value never resolves.
    """
    error = _error_object(output)
    if error is not None:
        for key in _ERROR_CODE_KEYS:
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                return value
    if isinstance(output, dict):
        for key in _ERROR_CODE_KEYS:
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _recovery_text(output: object) -> str | None:
    """The non-empty recovery/resolution instruction string, or None (R-08).

    Resolution order mirrors :func:`_error_code`: the structured ``error``
    dict, then the envelope top level.  The real AutoMedia error envelope uses
    ``resolution`` (``mcp_error.error_response``); ``recovery``/``remediation``/
    ``guidance``/``hint``/``instruction`` are accepted aliases.
    """
    error = _error_object(output)
    if error is not None:
        for key in _RECOVERY_KEYS:
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                return value
    if isinstance(output, dict):
        for key in _RECOVERY_KEYS:
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _trace_ids(value: object) -> list[str]:
    """Every non-empty trace/correlation identifier nested in ``value`` (Tr-01)."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key in _TRACE_ID_KEYS and isinstance(item, str) and item.strip():
                    found.append(item)
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return found


def _string_values(value: object) -> list[str]:
    """Every string nested in ``value`` (stdout JSON included)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _string_values(item)]
    if isinstance(value, list):
        return [text for item in value for text in _string_values(item)]
    return []


def _trace_id_failures(expected: str | bool, output: object) -> list[str]:
    """Grade ``expect.trace_id`` against an output envelope (Tr-01)."""
    ids = _trace_ids(output)
    if expected is True:
        if ids:
            return []
        return ["expect.trace_id: no non-empty trace_id/correlation_id field in output"]
    if expected is False:
        if not ids:
            return []
        return [f"expect.trace_id: expected no trace id, observed {_fmt(ids)}"]
    if expected in ids or any(expected in text for text in _string_values(output)):
        return []
    return [f"expect.trace_id: literal {expected!r} not found in output trace ids/strings"]
