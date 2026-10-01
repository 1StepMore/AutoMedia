#!/usr/bin/env python3
"""Static semantics check for GitHub Actions workflows — catches two real,
silent bug classes in this repo (plus one order-dependent evidence bug).

Third member of the repo-hygiene gate family (after
``scripts/check-doc-consistency.py`` and ``scripts/doc_inventory.py``):
``main()`` exits 0 when clean, 1 when any finding exists, accepts an optional
path argument defaulting to ``.github/workflows``, and prints ``file:line``
plus a one-line explanation per finding.

LAYERING DECISION (pinned — do NOT "fix" by adding a scenario):
``scenarios/`` exercises the PRODUCT surface through CLI/MCP per
``scenarios/STANDARDS.md``.  Workflow hygiene is REPO INFRASTRUCTURE, not
product behavior, so this invariant belongs here — as a repo gate wired like
its two siblings — and deliberately NOT as a validation scenario.

THE TWO BUG CLASSES (both observed live in this repo):

Rule 1 — stranded matrix conditional.  A step whose ``continue-on-error`` or
``if:`` is a ``matrix.<key>`` comparison that evaluates to a CONSTANT across
the job's own ``strategy.matrix`` combinations.  Constant ``true`` means the
step (often a whole suite) can never fail the job; constant ``false`` means the
apparent conditional is misleading.  Real instance: ``ci.yml`` job
``test-omni`` declares ``matrix: {python-version: ["3.13"]}`` and carries
``continue-on-error: ${{ matrix.python-version != '3.11' }}`` — permanently
true, so 133 Omni tests could never gate the build.  Root cause: commit
``dadf421`` (2026-07-18) narrowed the matrix and left the expression behind.

Rule 2 — phantom matrix key.  Any ``matrix.<key>`` reference in a step that the
job's own ``strategy.matrix`` does not declare.  Phantom keys are either typos
or stale matrix keys; GitHub silently yields empty/undefined.

Rule 3 — blocking scan before an unguarded test step.  Within a SINGLE job, a
security/vulnerability scan that is BLOCKING (no ``continue-on-error: true``)
and positioned before a LATER step in the same job that runs tests, where that
test step lacks both ``if: always()`` and ``if: !cancelled()``.  GitHub skips
later steps when an earlier one fails, so a red scan silently swallows the test
evidence.  Real instance: ``nightly.yml`` job ``full-test`` — L37 pip-audit and
L42 bandit are blocking and precede L82 ``Pytest (full suite)`` which has no
``if:``.  This already cost a real night of coverage (issue #91).

CRITICAL Rule 3 predicate (must NOT false-fire once the nightly fix lands):
the nightly fix adds ``if: !cancelled()`` to the test steps while deliberately
leaving the scans blocking — security must still block the WORKFLOW, it just
must not suppress test EVIDENCE.  So a blocking scan is a finding ONLY IF a
later step in the same job runs tests AND that later step lacks
``if: always()`` / ``if: !cancelled()``.  Guying the test step clears the
finding while the scan stays blocking; the job still fails overall on a red
scan.

Rule 4 — trusted-base file list that fails open when empty.  Within a SINGLE
job that checks out a PINNED base ref (not the default merge ref, and not the
PR's own head), a step that builds a changed-file list via ``git diff
--name-only`` must make an EMPTY list fatal before the list reaches a checker.
``set -e`` already covers a diff that FAILS; this covers the quieter case where
the diff SUCCEEDS with nothing in it, so the checker is handed an empty list.
Both repo checkers treat empty as "nothing to judge" and exit 0
(``check_release_scope.py``: "No changed files to judge";
``check_release_pr_guard.py``: "cannot judge, leaving it alone",
``snooze=false``), so an empty list turns a gate into a no-op that reports
success.  Real instances: ``conventional-commits.yml`` job ``release-scope``
(issue #137) and ``release-pr-guard.yml`` job ``guard``, whose freeze silently
stops firing when the tag range comes back empty.

A gate that fails CLOSED is noisy and safe; one that fails OPEN is silent and
is the more dangerous defect, which is why this rule exists.

PREDICATES (explicit, documented, not fuzzy):

* "is a security/vulnerability scan step" — the step ``name:`` matches
  ``(?i)\\b(security|vulnerabilit(y|ies)|vuln|audit|scan|sast|dast|secret scan)\\b``,
  OR the step ``uses:``/``run:`` payload references a known scanner tool.
  ENUMERATED scanner tool names: ``pip-audit``, ``bandit``, ``safety``,
  ``checkov``, ``trivy``, ``gitleaks``, and the local
  ``scripts/check-secrets.py``.
* "runs tests" — the step ``run:`` payload matches ``(?i)\\b(pytest|tox|nox)\\b``
  (which also covers ``-m pytest``), OR the step ``name:`` matches
  ``(?i)\\b(pytest|test suite|tests|unittest)\\b``.  A step that uses a
  third-party ``uses:`` action is NEVER a test step.
* "blocking" — the step does not carry ``continue-on-error: true``.  After YAML
  parsing that may be the bool ``True`` or the string ``'true'``; both are
  handled.  KNOWN LIMITATION: this is a purely step-level test, so it also
  counts a scan as blocking when the *tool* cannot actually fail the job — a
  step passing ``checkov --soft-fail``, or a scanner action invoked without an
  ``exit-code``, always exits 0.  Such a step can still be reported by Rule 3
  ahead of an unguarded test step.  The bias is deliberate and fail-safe (a
  non-failing scan in front of test evidence is surfaced for a human, not
  silently trusted), but it means a genuinely advisory scan placed before a
  test step needs the test step guarded rather than relying on the scan being
  harmless.  Tightening this would mean parsing each tool's own exit-code
  semantics, which is a larger contract than this gate should own.

SUPPORTED EXPRESSION GRAMMAR (honest, bounded): for Rules 1/2 the value is
unwrapped from an optional ``${{ ... }}`` wrapper and then must be exactly
``matrix.<key> == '<literal>'`` or ``matrix.<key> != '<literal>'`` (single or
double quoted literal).  Anything else that still references ``matrix.`` is
reported in a separate NON-FAILING "unverifiable by this guard" section —
never a false finding, never silently ignored.  Plain non-matrix expressions
are out of scope for these rules.  Bare ``!cancelled()`` (no quotes) parses via
a tolerant loader: PyYAML would otherwise read ``!`` as a YAML tag.

Matrix expansion: the cartesian product of every declared scalar value list is
evaluated (multiple keys supported).  ``include``/``exclude`` or any
object/list-valued matrix entry makes expansion unverifiable rather than
guessed, and the affected expressions are reported as unverifiable.

MALFORMED INPUT: a workflow that fails YAML parsing (or is not a mapping) is a
hard failure with a clear ``file: [PARSE] ...`` diagnostic — never silence.

ADVISORY vs HARD-FAIL (explicit decision): all three rules HARD-FAIL.  They are
deterministic over the supported grammar and cannot false-positive there
(unparseable shapes are diverted to the non-failing unverifiable section), so
no allowlist is needed.  A future legitimate single-combination conditional
should be rewritten, not allowlisted.

SIZE_OK: this module deliberately exceeds the 250-line guideline.  It owns ONE
concept — workflow-semantics checking — and the three rules share the same
parser, matrix expander and line index; splitting them would fragment a single
cohesive gate.  Same precedent as ``scripts/check-doc-consistency.py``.

Usage:
    python3 scripts/check-workflow-semantics.py [path]
    path defaults to ``.github/workflows`` (falling back to the repo copy when
    the default is missing from the current working directory).
"""

from __future__ import annotations

import argparse
import functools
import itertools
import re
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, SequenceNode

REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = ".github/workflows"

# --- Rule 3 predicates (see module docstring for the enumerated definitions) ---
_SCAN_NAME_RE = re.compile(
    r"(?i)\b(security|vulnerabilit(?:y|ies)|vuln|audit|scan|sast|dast|secret scan)\b"
)
_SCANNER_TOOL_RE = re.compile(
    r"(?i)(\b(?:pip-audit|bandit|safety|checkov|trivy|gitleaks)\b|scripts/check-secrets\.py)"
)
_TEST_RUN_RE = re.compile(r"(?i)\b(pytest|tox|nox)\b")
_TEST_NAME_RE = re.compile(r"(?i)\b(pytest|test suite|tests|unittest)\b")

# --- Supported matrix-expression grammar (see module docstring) ---
_MATRIX_REF_RE = re.compile(r"\bmatrix\.([A-Za-z_][A-Za-z0-9_-]*)")
_COMPARISON_RE = re.compile(
    r"^matrix\.(?P<key>[A-Za-z_][A-Za-z0-9_-]*)"
    r"\s*(?P<op>==|!=)\s*(?P<quote>['\"])(?P<literal>.*?)(?P=quote)$"
)
_SCALARS = (str, int, float, bool)


class WorkflowParseError(Exception):
    """A workflow file could not be parsed into the expected mapping shape."""


class _WorkflowLoader(yaml.SafeLoader):
    """``SafeLoader`` tolerant of GitHub's bare ``!cancelled()`` expressions.

    PyYAML reads a leading ``!`` as a YAML tag, so ``if: !cancelled()`` raises
    ``ConstructorError`` even though GitHub accepts the bare negation syntax.
    Unknown local ``!foo`` scalar tags therefore reconstruct to their literal
    ``!foo`` text instead of failing the scan; every known tag is untouched.
    """


def _construct_unknown_tag(_loader: _WorkflowLoader, tag_suffix: str, node: object) -> str:
    if isinstance(node, yaml.ScalarNode):
        return f"!{tag_suffix}{getattr(node, 'value', '')}"
    raise yaml.constructor.ConstructorError(
        None, None, f"unsupported non-scalar YAML tag: !{tag_suffix}", None
    )


_WorkflowLoader.add_multi_constructor("!", _construct_unknown_tag)


@dataclass(frozen=True)
class Finding:
    """One hard-failing workflow-semantics violation."""

    file: str
    line: int
    rule: str
    message: str


@dataclass(frozen=True)
class Unverifiable:
    """A matrix-referencing expression this bounded guard cannot evaluate."""

    file: str
    line: int
    detail: str


@dataclass(frozen=True)
class Analysis:
    """Findings (gate-failing) plus unverifiable expressions (informational)."""

    findings: tuple[Finding, ...]
    unverifiable: tuple[Unverifiable, ...]


@dataclass(frozen=True)
class ParsedWorkflow:
    """Parsed YAML data plus a path->line index for readable diagnostics."""

    data: Mapping[str, object]
    lines: Mapping[tuple[object, ...], int]


# --------------------------------------------------------------------------- #
# Small typed accessors over arbitrary YAML data (never `Any`)
# --------------------------------------------------------------------------- #


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _sequence(value: object) -> Sequence[object] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _iter_strings(value: object) -> Iterator[str]:
    """Yield every string leaf of a nested YAML value (values, not keys)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            yield from _iter_strings(item)


def _matrix_refs(value: str) -> tuple[str, ...]:
    """Ordered unique ``matrix.<key>`` key names referenced in ``value``."""
    return tuple(dict.fromkeys(_MATRIX_REF_RE.findall(value)))


def _line(parsed: ParsedWorkflow, path: tuple[object, ...]) -> int:
    return parsed.lines.get(path, 0)


# --------------------------------------------------------------------------- #
# Parsing + line index
# --------------------------------------------------------------------------- #


def _collect_line_index(node: object) -> dict[tuple[object, ...], int]:
    """Map each YAML node path to its 1-based start line (via ``yaml.compose``)."""
    index: dict[tuple[object, ...], int] = {}
    if node is None:
        return index

    def walk(current: object, path: tuple[object, ...]) -> None:
        start = getattr(current, "start_mark", None)
        if start is not None:
            index[path] = int(start.line) + 1
        if isinstance(current, MappingNode):
            for key_node, value_node in current.value:
                walk(value_node, (*path, getattr(key_node, "value", None)))
        elif isinstance(current, SequenceNode):
            for position, value_node in enumerate(current.value):
                walk(value_node, (*path, position))

    walk(node, ())
    return index


def parse_workflow(text: str, filename: str) -> ParsedWorkflow:
    """Parse one workflow document; raise ``WorkflowParseError`` on bad input."""
    try:
        node = yaml.compose(text, Loader=_WorkflowLoader)
    except yaml.YAMLError as exc:
        raise WorkflowParseError(f"{filename}: invalid YAML: {exc}") from exc
    loader = _WorkflowLoader(text)
    try:
        data: object = loader.get_single_data()
    except yaml.YAMLError as exc:
        raise WorkflowParseError(f"{filename}: invalid YAML: {exc}") from exc
    finally:
        loader.dispose()
    if not isinstance(data, Mapping):
        raise WorkflowParseError(f"{filename}: top-level YAML document is not a mapping")
    return ParsedWorkflow(data=data, lines=_collect_line_index(node))


# --------------------------------------------------------------------------- #
# Rule 1 — stranded matrix conditional
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Matrix:
    """Declared matrix keys plus expanded combos (``None`` = not expandable)."""

    keys: frozenset[str]
    combos: tuple[Mapping[str, str], ...] | None


def _extract_matrix(job: Mapping[str, object]) -> _Matrix:
    strategy = _mapping(job.get("strategy"))
    raw = _mapping(strategy.get("matrix")) if strategy is not None else None
    if raw is None:
        return _Matrix(frozenset(), ())
    base_keys = frozenset(k for k in raw if isinstance(k, str) and k not in ("include", "exclude"))
    if "include" in raw or "exclude" in raw:
        return _Matrix(base_keys, None)
    key_order: list[str] = []
    value_lists: list[list[str]] = []
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        values = _sequence(value)
        if not values:
            return _Matrix(base_keys, None)
        rendered: list[str] = []
        for item in values:
            if not isinstance(item, _SCALARS):
                return _Matrix(base_keys, None)
            rendered.append(str(item))
        key_order.append(key)
        value_lists.append(rendered)
    combos = tuple(
        dict(zip(key_order, combination, strict=True))
        for combination in itertools.product(*value_lists)
    )
    return _Matrix(frozenset(key_order), combos)


def _strip_expression(value: str) -> str:
    text = value.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    return text


def _parse_comparison(value: str) -> tuple[str, str, str] | None:
    match = _COMPARISON_RE.match(_strip_expression(value))
    if match is None:
        return None
    return match.group("key"), match.group("op"), match.group("literal")


def _compare(op: str, left: str, right: str) -> bool:
    return left == right if op == "==" else left != right


# --------------------------------------------------------------------------- #
# Rule 3 predicate helpers
# --------------------------------------------------------------------------- #


def _is_scan_step(step: Mapping[str, object]) -> bool:
    name = _text(step.get("name")) or ""
    if _SCAN_NAME_RE.search(name):
        return True
    payload = " ".join(filter(None, (_text(step.get("uses")), _text(step.get("run")))))
    return bool(_SCANNER_TOOL_RE.search(payload))


def _is_test_step(step: Mapping[str, object]) -> bool:
    if step.get("uses") is not None:
        return False
    run = _text(step.get("run")) or ""
    if _TEST_RUN_RE.search(run):
        return True
    return bool(_TEST_NAME_RE.search(_text(step.get("name")) or ""))


def _is_blocking(step: Mapping[str, object]) -> bool:
    value = step.get("continue-on-error")
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value.strip().lower() != "true"
    return True


def _has_suppression_guard(step: Mapping[str, object]) -> bool:
    value = _text(step.get("if"))
    if value is None:
        return False
    normalized = re.sub(r"\s+", "", value.replace("${{", "").replace("}}", ""))
    return "always()" in normalized or "!cancelled()" in normalized


def _step_name(step: Mapping[str, object]) -> str:
    name = _text(step.get("name"))
    if name:
        return name
    uses = _text(step.get("uses"))
    return uses if uses else "<unnamed step>"


# --------------------------------------------------------------------------- #
# Rule 4 predicates (see the module docstring for the contract)
# --------------------------------------------------------------------------- #

# A checkout ref that points at the PR's own head is NOT the hazard: HEAD then
# *is* the PR, so diffing against the base yields the real PR file list.
_PR_REF_MARKERS = ("refs/pull", "github.event.pull_request.head", "github.head_ref")


def _pins_trusted_base(step: Mapping[str, object]) -> bool:
    """True when a checkout pins an explicit ref that is not the PR's own head.

    Pinning a base ref is what makes Rule 4's hazard possible: once the
    workspace is a known base, the diff's far endpoint no longer follows the
    PR, so the computed file list can come back empty for reasons that have
    nothing to do with the PR having no changes.
    """
    uses = _text(step.get("uses"))
    if uses is None or "actions/checkout" not in uses:
        return False
    options = _mapping(step.get("with"))
    if options is None:
        return False
    ref = _text(options.get("ref"))
    if ref is None:
        return False  # default resolves to the merge ref; HEAD is the PR
    return not any(marker in _strip_expression(ref) for marker in _PR_REF_MARKERS)


def _builds_file_list(run: str) -> bool:
    return "git diff" in run and ("--name-only" in run or "--name-status" in run)


def _exit_status(token: str) -> int | None:
    """Exit code an ``exit <token>`` will produce, or None if not statically known."""
    cleaned = token.strip("\"';)")
    if cleaned.isdigit():
        return int(cleaned)
    return None


def _empty_list_is_fatal(run: str) -> bool:
    """True when the run makes an empty ``$FILES`` abort before the checker runs.

    Two accepted idioms, both required to be provably fatal:
    an emptiness test (``-z``/``test -z``) followed by a non-zero ``exit``, or a
    ``|| exit <non-zero>`` chained onto the assignment that captured the list.
    """
    for assign in re.finditer(r"\|\|\s*exit\s+(\S+)", run):
        status = _exit_status(assign.group(1))
        if status is not None and status != 0:
            return True
    for test in re.finditer(r"(?:^|[\s\[(])-{1,2}z\b|\btest\s+-z\b", run):
        for exit_match in re.finditer(r"\bexit\s+(\S+)", run[test.end() :]):
            status = _exit_status(exit_match.group(1))
            if status is not None and status != 0:
                return True
    return False


def _guards_empty_list(run: str) -> bool:
    """True when the run proves an empty list cannot reach the checker.

    The diff failing outright is already covered by ``set -e``; this covers the
    quieter case where the diff SUCCEEDS with nothing in it.
    """
    if _empty_list_is_fatal(run):
        return True
    # ``[ -s file ] && exit 1`` — rejects an empty captured file by size.
    return bool(re.search(r"!\s*-s\b|-s\b[^\n]*&&\s*exit\s+[^0\s]", run))


# --------------------------------------------------------------------------- #
# Detectors (pure: parsed data in, Analysis out — no filesystem, no subprocess)
# --------------------------------------------------------------------------- #


def _check_rule1(
    step: Mapping[str, object],
    matrix: _Matrix,
    line: int,
    filename: str,
    findings: list[Finding],
    unverifiable: list[Unverifiable],
) -> None:
    name = _step_name(step)
    for field in ("continue-on-error", "if"):
        value = _text(step.get(field))
        if value is None or not _matrix_refs(value):
            continue
        if any(ref not in matrix.keys for ref in _matrix_refs(value)):
            continue  # phantom key — reported by Rule 2, not an evaluable conditional
        comparison = _parse_comparison(value)
        if comparison is None:
            unverifiable.append(
                Unverifiable(
                    filename,
                    line,
                    f"step '{name}' {field} references matrix but its expression shape is "
                    f"not supported by this guard: {value.strip()!r}",
                )
            )
            continue
        if matrix.combos is None:
            unverifiable.append(
                Unverifiable(
                    filename,
                    line,
                    f"step '{name}' {field}: matrix uses include/exclude or object values; "
                    "combinations cannot be expanded",
                )
            )
            continue
        key, op, literal = comparison
        results = {_compare(op, combo[key], literal) for combo in matrix.combos}
        if len(results) != 1:
            continue
        constant = next(iter(results))
        declared = ", ".join(sorted(matrix.keys))
        if field == "continue-on-error" and constant:
            consequence = "the step can never fail the job"
        elif field == "continue-on-error":
            consequence = "continue-on-error is permanently false (the expression is misleading)"
        else:
            consequence = "the conditional is constant and cannot branch"
        findings.append(
            Finding(
                filename,
                line,
                "R1",
                f"step '{name}' {field} expression {value.strip()!r} is constant "
                f"{constant} across matrix [{declared}] — {consequence}",
            )
        )


def _check_rule2(
    step: Mapping[str, object],
    matrix: _Matrix,
    line: int,
    filename: str,
    findings: list[Finding],
) -> None:
    name = _step_name(step)
    seen: set[str] = set()
    for text in _iter_strings(step):
        for ref in _matrix_refs(text):
            if ref in matrix.keys or ref in seen:
                continue
            seen.add(ref)
            declared = ", ".join(sorted(matrix.keys)) or "<none>"
            findings.append(
                Finding(
                    filename,
                    line,
                    "R2",
                    f"step '{name}' references matrix.{ref} but the job matrix does not "
                    f"declare it (declared: {declared})",
                )
            )


def _check_rule3(
    steps: Sequence[object],
    line_of: Callable[[int], int],
    filename: str,
    findings: list[Finding],
) -> None:
    for index, step_value in enumerate(steps):
        step = _mapping(step_value)
        if step is None or not _is_scan_step(step) or not _is_blocking(step):
            continue
        scan_name = _step_name(step)
        for later_index in range(index + 1, len(steps)):
            later = _mapping(steps[later_index])
            if later is None or not _is_test_step(later) or _has_suppression_guard(later):
                continue
            findings.append(
                Finding(
                    filename,
                    line_of(index),
                    "R3",
                    f"blocking scan step '{scan_name}' precedes test step "
                    f"'{_step_name(later)}' (line {line_of(later_index)}) which lacks "
                    "`if: always()` / `if: !cancelled()`; a red scan silently skips the "
                    "test evidence",
                )
            )
            break


def _check_rule4(
    steps: Sequence[object],
    line_of: Callable[[int], int],
    filename: str,
    findings: list[Finding],
) -> None:
    if not any(
        _pins_trusted_base(step)
        for step in (_mapping(value) for value in steps)
        if step is not None
    ):
        return
    for index, step_value in enumerate(steps):
        step = _mapping(step_value)
        if step is None:
            continue
        run = _text(step.get("run"))
        if run is None or not _builds_file_list(run) or _guards_empty_list(run):
            continue
        findings.append(
            Finding(
                filename,
                line_of(index),
                "R4",
                f"step '{_step_name(step)}' builds a changed-file list with git diff in a "
                "job that checks out a pinned base ref, but never fails when that list is "
                "empty; an empty diff (stale tag, bad ref, truncated fetch) reaches the "
                "checker, which reports 'nothing to judge' and exits 0 — the gate fails open",
            )
        )


def _step_line(parsed: ParsedWorkflow, job_name: object, index: int) -> int:
    return _line(parsed, ("jobs", job_name, "steps", index))


def analyze_workflow(parsed: ParsedWorkflow, filename: str) -> Analysis:
    """Pure detector over parsed workflow data.  No I/O, no subprocess."""
    jobs = _mapping(parsed.data.get("jobs"))
    if jobs is None:
        return Analysis((), ())
    findings: list[Finding] = []
    unverifiable: list[Unverifiable] = []
    for job_name, job_value in jobs.items():
        job = _mapping(job_value)
        steps = _sequence(job.get("steps")) if job is not None else None
        if job is None or steps is None:
            continue
        matrix = _extract_matrix(job)
        line_of = functools.partial(_step_line, parsed, job_name)
        for index, step_value in enumerate(steps):
            step = _mapping(step_value)
            if step is None:
                continue
            line = line_of(index)
            _check_rule1(step, matrix, line, filename, findings, unverifiable)
            _check_rule2(step, matrix, line, filename, findings)
        _check_rule3(steps, line_of, filename, findings)
        _check_rule4(steps, line_of, filename, findings)
    return Analysis(tuple(findings), tuple(unverifiable))


def analyze_text(text: str, filename: str) -> Analysis:
    """Parse ``text`` and run the pure detector (raises ``WorkflowParseError``)."""
    return analyze_workflow(parse_workflow(text, filename), filename)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_root(arg: str | None) -> Path | None:
    if arg is not None:
        candidate = Path(arg)
        return candidate if candidate.exists() else None
    for candidate in (Path.cwd() / _DEFAULT_PATH, REPO_ROOT / _DEFAULT_PATH):
        if candidate.is_dir():
            return candidate
    return None


def _workflow_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if root.is_dir():
        return sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")], key=lambda p: p.as_posix())
    return []


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checker; return 0 when clean, 1 when any finding exists."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help=(
            "Workflow file or directory to scan. Defaults to .github/workflows "
            "(falls back to the repo copy when the default is missing locally)."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = _resolve_root(args.path)
    if root is None:
        print(f"FAIL: no workflow path found at {args.path!r} and no default {_DEFAULT_PATH}")
        return 1
    files = _workflow_files(root)
    if not files:
        print(f"FAIL: no workflow YAML files found under {_label(root)}")
        return 1

    findings: list[Finding] = []
    unverifiable: list[Unverifiable] = []
    for path in files:
        label = _label(path)
        try:
            analysis = analyze_text(path.read_text(encoding="utf-8"), label)
        except (OSError, WorkflowParseError) as exc:
            findings.append(Finding(label, 0, "PARSE", f"could not parse workflow: {exc}"))
            continue
        findings.extend(analysis.findings)
        unverifiable.extend(analysis.unverifiable)

    for finding in findings:
        print(f"{finding.file}:{finding.line}: [{finding.rule}] {finding.message}")

    if unverifiable:
        print(f"\nUNVERIFIABLE by this guard (informational — never gates) — {len(unverifiable)}:")
        for item in unverifiable:
            print(f"  {item.file}:{item.line}: {item.detail}")

    if findings:
        print(f"\nFAIL: {len(findings)} workflow-semantics finding(s)")
        return 1
    print(f"\nOK: no workflow-semantics findings in {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
