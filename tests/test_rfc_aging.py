"""RFC aging gate: ``Proposed`` RFCs must stay current (issue #286).

The gate exists because #286 shipped a script that printed its findings and
then exited 0 — a check that could never fail.  These tests pin the three
things that made it useless: the exit code, the metric derivation, and the
tolerance band that keeps prose rounding from going red.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module() -> ModuleType:
    name = "check_rfc_aging"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "check_rfc_aging.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # @dataclass-free, but keep the loader contract uniform
    spec.loader.exec_module(module)
    return module


def _runner(tmp_path: Path, lines: int) -> Path:
    path = tmp_path / "src" / "automedia" / "pipelines" / "runner.py"
    path.parent.mkdir(parents=True)
    path.write_text("x = 1\n" * lines, encoding="utf-8")
    return path


def _rfc(tmp_path: Path, body: str, name: str = "deep-module-rfc-999.md") -> Path:
    path = tmp_path / "docs" / "dev" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The exit code IS the gate: this is what #286 got wrong
# ---------------------------------------------------------------------------


def test_main_fails_when_metrics_drift(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 100)
    _rfc(
        tmp_path,
        "**Status:** Proposed\n**Date:** 2026-10-23\n999 lines runner.py\n",
    )

    original = module.REPO_ROOT
    module.REPO_ROOT = tmp_path
    try:
        assert module.main(["--max-age-days", "9000"]) == 1
    finally:
        module.REPO_ROOT = original


def test_main_passes_when_everything_is_current(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 100)
    _rfc(
        tmp_path,
        "**Status:** Proposed\n**Date:** 2026-10-23\n100 lines runner.py\n",
    )

    # main() reads the real repo through the module REPO_ROOT; point it at the
    # synthetic tree so the assertion is about exit codes, not this repo.
    original = module.REPO_ROOT
    module.REPO_ROOT = tmp_path
    try:
        assert module.main(["--max-age-days", "9000"]) == 0
    finally:
        module.REPO_ROOT = original


def test_main_fails_on_an_overdue_proposal(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 100)
    _rfc(tmp_path, "**Status:** Proposed\n**Date:** 2020-01-01\n100 lines runner.py\n")

    original = module.REPO_ROOT
    module.REPO_ROOT = tmp_path
    try:
        assert module.main(["--max-age-days", "90"]) == 1
    finally:
        module.REPO_ROOT = original


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def test_fresh_rfc_with_current_metrics_reports_nothing(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 100)
    _rfc(tmp_path, "**Status:** Proposed\n**Date:** 2026-10-23\n100 lines runner.py\n")

    assert module.propose_aging_findings(proposed_max_age_days=9_000, root=tmp_path) == []


def test_stale_metrics_are_reported_per_metric(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 1_000)
    _rfc(
        tmp_path,
        "**Status:** Proposed\n**Date:** 2026-10-23\n"
        "100 lines runner.py; 7 functions; 99 function-level lazy imports\n",
    )

    findings = module.propose_aging_findings(proposed_max_age_days=9_000, root=tmp_path)

    assert len(findings) == 3
    assert "lines 100 vs actual 1000" in findings[0]
    assert "functions 7 vs actual 0" in findings[1]
    assert "lazy_imports 99 vs actual 0" in findings[2]


def test_rounding_within_tolerance_is_not_a_finding(tmp_path: Path) -> None:
    """Prose says "~1,600"; the file has 1,617. That must not go red."""
    module = _load_module()
    _runner(tmp_path, 1_617)
    _rfc(tmp_path, "**Status:** Proposed\n**Date:** 2026-10-23\n1,600 lines runner.py\n")

    assert module.propose_aging_findings(proposed_max_age_days=9_000, root=tmp_path) == []


def test_drift_beyond_tolerance_is_a_finding(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 2_309)
    _rfc(tmp_path, "**Status:** Proposed\n**Date:** 2026-10-23\n1,617 lines runner.py\n")

    findings = module.propose_aging_findings(proposed_max_age_days=9_000, root=tmp_path)

    assert len(findings) == 1
    assert "recorded runner.py lines 1617 vs actual 2309" in findings[0]


def test_non_proposed_rfc_is_ignored(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 100)
    _rfc(
        tmp_path,
        "**Status:** Adopted\n**Date:** 2020-01-01\n999 lines runner.py\n",
    )

    assert module.propose_aging_findings(proposed_max_age_days=90, root=tmp_path) == []


def test_missing_status_header_is_a_finding(tmp_path: Path) -> None:
    module = _load_module()
    _runner(tmp_path, 100)
    _rfc(tmp_path, "No header here.\n")

    findings = module.propose_aging_findings(proposed_max_age_days=90, root=tmp_path)

    assert findings == ["deep-module-rfc-999.md: missing **Status:** header"]


# ---------------------------------------------------------------------------
# Derivation contract
# ---------------------------------------------------------------------------


def test_runner_metrics_count_only_top_level_functions(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "src" / "automedia" / "pipelines" / "runner.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from __future__ import annotations\n"
        "\n"
        "def top_level() -> None:\n"
        "    from automedia.core.llm_client import llm_complete\n"
        "    def nested() -> None:\n"
        "        pass\n"
        "    nested()\n"
        "\n"
        "def second() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    original = module.REPO_ROOT
    module.REPO_ROOT = tmp_path
    try:
        metrics = module._runner_metrics()
    finally:
        module.REPO_ROOT = original

    assert metrics["functions"] == 2  # nested() is implementation detail
    assert metrics["lazy_imports"] == 1


@pytest.mark.parametrize(
    "recorded,actual,stale",
    [
        (1_600, 1_617, False),  # prose rounding
        (1_617, 2_309, True),  # RFC-001's real drift
        (100, 104, False),  # inside the absolute floor
        (100, 130, True),  # 23% — a real refactor
    ],
)
def test_tolerance_band(recorded: int, actual: int, stale: bool) -> None:
    module = _load_module()

    assert module._is_stale(recorded, actual) is stale
