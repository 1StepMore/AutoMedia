"""RED contract tests for the doc-consistency checker seam.

Plan: ``doc-hardening-pass2``, Step 2 (RED phase).  These tests define the
CONTRACT that Step 3 implements inside ``scripts/check-doc-consistency.py``
(the ``scan_links`` / ``scan_identifiers`` / ``scan_marker`` pure functions
extracted in Step 1, commit ``42dc211``).  They must FAIL today (RED) for the
not-yet-implemented parts and PASS after Step 3 lands (GREEN).

Current RED / GREEN split (verified against the Step 1 seam):

- GREEN already (Step 1 implemented the core): ``scan_links`` link-existence
  tests and the ``_scan_file`` numeric-claim regression.
- RED today: ``scan_identifiers`` and ``scan_marker`` are stubs returning
  ``[]``, so the tests that expect 1 Finding fail.  Additionally the
  non-Python-token test (``test_scan_identifiers_non_python_tokens_...``)
  asserts the resolver is CONSULTED for real Python symbols — the stub never
  calls the resolver, so that assertion fails RED too.

CONTRACT PINS (Step 3 must honor these; each is documented on its test):

1. All ``scan_*`` functions are PURE: they return ``list[Finding]`` and set
   ``Finding.file == ""`` — the caller (``main()``) fills in the real path.
   The CALLER decides severity (gate-failing vs informational); the functions
   only report candidates.

2. ``scan_links(text, base)``: only root-relative ``docs/``-prefixed link
   targets are probed against ``base`` (repo root).  External URLs and
   ``#anchor`` links are ignored (never findings).  A missing target yields
   exactly one Finding whose ``line`` is the 1-based source line.

3. ``scan_identifiers(text, resolver)``: ``resolver(name) -> bool`` returns
   True when the symbol resolves (exists).  The exclusion-set filter (MCP
   tool names from ``doc_reality_audit()`` declared-tools, CLI command names,
   env var names, ``AUTOMEDIA_*``, YAML keys from
   ``manifests/defaults.yaml``, workflow modes, plus any committed allowlist
   entries) is applied INSIDE ``scan_identifiers`` BEFORE the resolver is
   consulted.  Non-Python tokens such as ``deepseek``, ``expect`` and
   ``failure_mode`` are in that exclusion set and therefore NEVER reach the
   resolver and NEVER appear in the returned findings.  Only candidates that
   survive the filters and are REJECTED by the resolver produce a Finding
   (one per occurrence, ``line`` = 1-based source line).  A candidate the
   resolver ACCEPTS produces no Finding.

4. ``scan_marker(text, marker)``: the marker must be the exact first line of
   ``text`` (byte equality).  A mismatch — including a missing marker — yields
   exactly one Finding at ``line == 1``.

5. The numeric-claim check stays regression-locked: ``_scan_file(path,
   tool_count, command_count)`` catches a mis-set tool count.

Loader note (from Step 1 learnings): ``scripts/`` has no ``__init__.py``, so
the checker cannot be plain-imported.  It is loaded via
``importlib.util.spec_from_file_location`` and — CRITICAL — must be
registered in ``sys.modules[spec.name]`` BEFORE ``exec_module``, otherwise the
frozen ``@dataclass`` crashes (``_is_type`` resolves ``cls.__module__`` in
``sys.modules``).  Loading the module does import ``automedia.cli.app``,
``automedia.mcp.server`` and ``automedia.validation.doc_reality`` (the repo's
own package) — acceptable and intended.

NOTE on the loader path arithmetic: the step-2 brief's snippet used
``parent.parent.parent``, but this test file lives at
``tests/test_doc_consistency.py`` (one level under the repo root), so the
repo root is ``Path(__file__).resolve().parent.parent``.

All fixtures are synthetic (Red Line 4): ``tests/fixtures/synth/doccheck/``
only — never production docs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-doc-consistency.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "synth" / "doccheck"

# Exact first line required on generated inventory files (plan item 1c / 3).
MARKER = (
    "<!-- AUTO-GENERATED: docs/doc-inventory.md — do not edit manually. "
    "Regenerate: python scripts/doc_inventory.py -->"
)


# ---------------------------------------------------------------------------
# Checker loader (session-scoped: the real script, loaded once)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def checker() -> ModuleType:
    """Load the real ``scripts/check-doc-consistency.py`` module (once)."""
    if "check_doc_consistency" in sys.modules:
        return sys.modules["check_doc_consistency"]
    if not SCRIPT.is_file():
        pytest.fail(f"checker script missing: {SCRIPT}")
    spec = importlib.util.spec_from_file_location("check_doc_consistency", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # MUST register before exec_module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _read(name: str) -> str:
    """Read a synthetic fixture by name."""
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# scan_links — GREEN today (Step 1 implemented the core); pins the contract
# ---------------------------------------------------------------------------


def test_scan_links_ok(checker: ModuleType) -> None:
    """Valid root-relative links, external URLs and anchors produce no findings.

    Contract: ``scan_links`` probes only ``docs/``-prefixed root-relative
    targets; ``https://example.com`` (external) and ``docs/index.md#section``
    (anchored) are never findings, even when the destination file exists.
    """
    findings = checker.scan_links(_read("links-ok.md"), REPO_ROOT)
    assert findings == []


def test_scan_links_broken(checker: ModuleType) -> None:
    """A missing root-relative target yields exactly one Finding at its line.

    ``links-broken.md``: ``docs/index.md`` resolves; ``docs/nonexistent-file.md``
    (line 7) does not.  ``Finding.file`` stays ``""`` (pure function — the
    caller fills in the real path); ``Finding.line`` is the 1-based line.
    """
    findings = checker.scan_links(_read("links-broken.md"), REPO_ROOT)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.line == 7
    assert finding.file == ""
    assert "docs/nonexistent-file.md" in finding.found
    assert finding.expected  # non-empty description of what was expected


# ---------------------------------------------------------------------------
# scan_identifiers — RED today (stub returns []); pins the exclusion contract
# ---------------------------------------------------------------------------


def test_scan_identifiers_stale(checker: ModuleType) -> None:
    """A resolver-rejected symbol produces exactly one Finding at its line.

    Contract: ``scan_identifiers(text, resolver)`` returns one Finding per
    candidate that survives the exclusion filter AND is rejected by
    ``resolver(name)`` (the symbol does not resolve).  ``identifiers-stale.md``
    has ``run_full_pipeline`` (resolver-accepted) and ``nonexistent_module_xyz``
    (line 4, resolver-rejected) — so exactly 1 Finding, pointing at line 4.
    """
    def resolver(name: str) -> bool:
        return name == "run_full_pipeline"

    findings = checker.scan_identifiers(_read("identifiers-stale.md"), resolver)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.line == 4
    assert "nonexistent_module_xyz" in finding.found
    assert finding.file == ""
    assert finding.expected  # non-empty description of what was expected


def test_scan_identifiers_non_python_tokens_are_not_gate_failing(checker: ModuleType) -> None:
    """Non-Python tokens never produce findings and never reach the resolver.

    This is the plan's bounded-scope pin (plan item 1b): the exclusion-set
    filter lives INSIDE ``scan_identifiers``, BEFORE the resolver.  The three
    non-Python tokens ``deepseek``, ``expect``, ``failure_mode`` are in that
    exclusion set, so they are filtered out before resolution.

    The resolver here accepts ``run_full_pipeline`` / ``GateEngine`` (both
    exist) and rejects everything else.  Two assertions make the contract
    observable:

    - ``findings == []`` — the non-Python tokens produce NO findings, even
      though a naive resolver would reject them.  (The CALLER decides
      severity; these never reach the returned list.)
    - ``set(calls) == {"run_full_pipeline", "GateEngine"}`` — the resolver is
      consulted ONLY for the real Python-symbol candidates and is NEVER
      called with an excluded non-Python token.  This is what makes the test
      RED today: the stub returns ``[]`` without ever calling the resolver,
      so the call-set assertion fails.

    If Step 3 instead consulted the resolver for non-Python tokens (no
    exclusion filter inside ``scan_identifiers``), the resolver would be
    called with ``deepseek``/``expect``/``failure_mode`` and the call-set
    assertion fails — pinning the filter-inside-the-function design.
    """
    calls: list[str] = []

    def resolver(name: str) -> bool:
        calls.append(name)
        return name in {"run_full_pipeline", "GateEngine"}

    findings = checker.scan_identifiers(_read("identifiers-ok.md"), resolver)
    assert findings == []
    assert set(calls) == {"run_full_pipeline", "GateEngine"}


# ---------------------------------------------------------------------------
# scan_marker — RED today (stub returns []); pins the first-line marker contract
# ---------------------------------------------------------------------------


def test_scan_marker_ok(checker: ModuleType) -> None:
    """A file whose first line is exactly the marker yields no findings."""
    findings = checker.scan_marker(_read("marker-ok.md"), MARKER)
    assert findings == []


def test_scan_marker_missing(checker: ModuleType) -> None:
    """A file missing the first-line marker yields exactly one Finding at line 1.

    Contract: the marker must be the exact first line of ``text`` (byte
    equality, including the em-dash).  ``marker-missing.md`` starts with
    ``# Marker Missing ...``, so the check flags it once at ``line == 1``.
    """
    findings = checker.scan_marker(_read("marker-missing.md"), MARKER)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.line == 1
    assert finding.file == ""
    assert finding.found == _read("marker-missing.md").splitlines()[0]
    assert finding.expected  # non-empty description of what was expected


# ---------------------------------------------------------------------------
# Regression — numeric-claim check (GREEN today; must stay locked)
# ---------------------------------------------------------------------------


def test_scan_file_regression_mis_set_tool_count(checker: ModuleType, tmp_path: Path) -> None:
    """The numeric-claim check still catches a mis-set tool count.

    ``_scan_file(path, tool_count, command_count)`` must flag a doc claiming
    ``99 tools`` when the derived tool count is 65 (the current real count),
    returning exactly one Finding on the claiming line.
    """
    claims = tmp_path / "claims.md"
    claims.write_text("The MCP server exposes 99 tools.\n", encoding="utf-8")
    findings = checker._scan_file(claims, tool_count=65, command_count=19)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.line == 1
    assert finding.found == "99 tools"
    assert finding.expected == "65 tools"
