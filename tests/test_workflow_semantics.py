"""Contract tests for ``scripts/check-workflow-semantics.py``.

SYNTHETIC-ONLY: every fixture below is an inline YAML string written to
``tmp_path`` (or fed straight to the pure detector).  No test reads the real
``.github/workflows/`` tree — repo red line: zero production data in tests.
The fixtures pin the DETECTOR's behavior, not the current contents of the
real workflows (which a concurrent agent owns).

Coverage contract (explicit expected finding counts):

* stranded matrix conditional   -> 1 finding (rule R1)
* varied matrix conditional      -> 0 findings
* phantom matrix key             -> 1 finding (rule R2)
* blocking scan before unguarded test -> 1 finding (rule R3)
* blocking scan before GUARDED test   -> 0 findings  (regression lock for the
  concurrent nightly fix: ``if: !cancelled()`` on the test step clears it while
  the scan stays blocking)
* non-scan blocking step before test   -> 0 findings
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "check_workflow_semantics",
    _REPO_ROOT / "scripts" / "check-workflow-semantics.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_WF = importlib.util.module_from_spec(_SPEC)
# Register before exec: @dataclass resolves cls.__module__ via sys.modules.
sys.modules[_SPEC.name] = _WF
_SPEC.loader.exec_module(_WF)


# --------------------------------------------------------------------------- #
# Synthetic workflow fixtures
# --------------------------------------------------------------------------- #

_STRANDED = """
name: stranded
on: [push]
jobs:
  test-omni:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.13"]
    steps:
      - uses: actions/checkout@v7
      - name: Run Omni adapter tests
        continue-on-error: ${{ matrix.python-version != '3.11' }}
        run: python3 -m pytest tests/test_omni/ -v
"""

_VARIED = """
name: varied
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v7
      - name: Pytest
        continue-on-error: ${{ matrix.python-version != '3.11' }}
        run: python3 -m pytest -q
"""

_PHANTOM = """
name: phantom
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]
    steps:
      - name: Pytest
        if: ${{ matrix.foo == 'bar' }}
        run: python3 -m pytest -q
"""

_SCAN_BEFORE_UGUARDED = """
name: nightly
on: [push]
jobs:
  full-test:
    runs-on: ubuntu-latest
    steps:
      - name: Security scan (pip-audit)
        run: |
          pip install pip-audit
          pip-audit
      - name: Pytest (full suite)
        run: python3 -m pytest -q
"""

_SCAN_BEFORE_GUARDED_TEMPLATE = """
name: nightly
on: [push]
jobs:
  full-test:
    runs-on: ubuntu-latest
    steps:
      - name: Security scan (pip-audit)
        run: pip-audit
      - name: Pytest (full suite)
        if: {guard}
        run: python3 -m pytest -q
"""

_NON_SCAN_BEFORE_TEST = """
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Pytest
        run: python3 -m pytest -q
"""

_ADVISORY_SCAN_BEFORE_TEST = """
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Security scan (bandit)
        continue-on-error: {advisory}
        run: bandit -r src/
      - name: Pytest
        run: python3 -m pytest -q
"""

_CONSTANT_FALSE_IF = """
name: stranded-if
on: [push]
jobs:
  test-omni:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.13"]
    steps:
      - name: Only on 3.11
        if: matrix.python-version == '3.11'
        run: python3 -m pytest -q
"""

_UNSUPPORTED_EXPRESSION = """
name: unsupported
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - name: Pytest
        if: ${{ matrix.python-version }}
        run: python3 -m pytest -q
"""

_OBJECT_VALUED_MATRIX = """
name: object-valued
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        os: [ubuntu-latest]
        settings:
          - key: value
    steps:
      - name: Pytest
        if: ${{ matrix.settings == 'x' }}
        run: python3 -m pytest -q
"""

_TWO_KEY_MATRIX = """
name: two-key
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.13"]
    steps:
      - name: Pytest
        continue-on-error: ${{ matrix.python-version != '3.11' }}
        run: python3 -m pytest -q
"""

_USES_STEP_NAMED_TESTS = """
name: uses-not-test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Security scan (pip-audit)
        run: pip-audit
      - name: Run tests action
        uses: some-org/pytest-action@v1
"""


def _analyze(text: str, name: str = "fixture.yml") -> object:
    return _WF.analyze_text(text, name)


# --------------------------------------------------------------------------- #
# Rule 1 — stranded matrix conditional
# --------------------------------------------------------------------------- #


def test_stranded_matrix_conditional_is_one_finding() -> None:
    analysis = _analyze(_STRANDED)

    assert len(analysis.findings) == 1
    assert analysis.findings[0].rule == "R1"


def test_varied_matrix_conditional_is_clean() -> None:
    analysis = _analyze(_VARIED)

    assert len(analysis.findings) == 0


def test_constant_false_if_is_still_a_finding() -> None:
    # matrix is ["3.13"], so `== '3.11'` is permanently False: a misleading
    # conditional, not a gate.  Constant false is a finding too.
    analysis = _analyze(_CONSTANT_FALSE_IF)

    assert len(analysis.findings) == 1
    assert analysis.findings[0].rule == "R1"


def test_two_key_matrix_uses_cartesian_product() -> None:
    # Two matrix keys; the referenced key's value is constant across the
    # product, so the conditional is stranded.
    analysis = _analyze(_TWO_KEY_MATRIX)

    assert len(analysis.findings) == 1
    assert analysis.findings[0].rule == "R1"


# --------------------------------------------------------------------------- #
# Rule 2 — phantom matrix key
# --------------------------------------------------------------------------- #


def test_phantom_matrix_key_is_one_finding() -> None:
    analysis = _analyze(_PHANTOM)

    assert len(analysis.findings) == 1
    assert analysis.findings[0].rule == "R2"


def test_phantom_reference_is_not_also_reported_as_stranded() -> None:
    # The undeclared key is a phantom, not an evaluable conditional; rule 1
    # must not double-count it.
    analysis = _analyze(_PHANTOM)

    assert [f.rule for f in analysis.findings] == ["R2"]


# --------------------------------------------------------------------------- #
# Rule 3 — blocking scan before an unguarded test step
# --------------------------------------------------------------------------- #


def test_blocking_scan_before_unguarded_test_is_one_finding() -> None:
    analysis = _analyze(_SCAN_BEFORE_UGUARDED)

    assert len(analysis.findings) == 1
    assert analysis.findings[0].rule == "R3"


@pytest.mark.parametrize(
    "guard",
    ["${{ !cancelled() }}", "!cancelled()", "always()", '"!cancelled()"'],
)
def test_blocking_scan_before_guarded_test_is_clean(guard: str) -> None:
    # REGRESSION LOCK for the concurrent nightly.yml fix: the scan stays
    # blocking, but the test step is guarded, so evidence is no longer
    # suppressed -> zero findings.
    text = _SCAN_BEFORE_GUARDED_TEMPLATE.format(guard=guard)

    analysis = _analyze(text)

    assert len(analysis.findings) == 0


def test_non_scan_blocking_step_before_test_is_clean() -> None:
    analysis = _analyze(_NON_SCAN_BEFORE_TEST)

    assert len(analysis.findings) == 0


@pytest.mark.parametrize("advisory", ["true", "'true'"])
def test_advisory_scan_before_test_is_clean(advisory: str) -> None:
    # `continue-on-error: true` (bool) and `'true'` (string) both mean the scan
    # cannot fail the job, so it cannot suppress the test.
    text = _ADVISORY_SCAN_BEFORE_TEST.format(advisory=advisory)

    analysis = _analyze(text)

    assert len(analysis.findings) == 0


def test_uses_step_is_never_a_test_step() -> None:
    analysis = _analyze(_USES_STEP_NAMED_TESTS)

    assert len(analysis.findings) == 0


# --------------------------------------------------------------------------- #
# Unverifiable expressions — reported, never gate-failing
# --------------------------------------------------------------------------- #


def test_unsupported_matrix_expression_is_unverifiable_not_finding() -> None:
    analysis = _analyze(_UNSUPPORTED_EXPRESSION)

    assert len(analysis.findings) == 0
    assert len(analysis.unverifiable) == 1


def test_object_valued_matrix_is_unverifiable_and_not_phantom() -> None:
    # A declared key with an object/list value cannot be expanded; it must be
    # unverifiable, never misreported as a phantom key.
    analysis = _analyze(_OBJECT_VALUED_MATRIX)

    assert len(analysis.findings) == 0
    assert len(analysis.unverifiable) == 1


# --------------------------------------------------------------------------- #
# CLI / parser surface
# --------------------------------------------------------------------------- #


def test_main_returns_zero_on_clean_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "clean.yml").write_text(_VARIED, encoding="utf-8")

    assert _WF.main([str(tmp_path)]) == 0
    assert "OK:" in capsys.readouterr().out


def test_main_returns_one_on_findings_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "stranded.yml").write_text(_STRANDED, encoding="utf-8")

    assert _WF.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "R1" in out


def test_main_reports_malformed_yaml_without_silence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.yml").write_text("jobs: [unclosed\n", encoding="utf-8")

    assert _WF.main([str(tmp_path)]) == 1
    assert "bad.yml" in capsys.readouterr().out


def test_parse_workflow_rejects_non_mapping_document() -> None:
    with pytest.raises(_WF.WorkflowParseError):
        _WF.parse_workflow("- just\n- a\n- list\n", "list.yml")
