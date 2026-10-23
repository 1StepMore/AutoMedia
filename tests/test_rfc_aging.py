"""RFC aging checks stay green and catch drift (issue #286)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_rfc_aging", REPO_ROOT / "scripts" / "check_rfc_aging.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_rfc_with_current_metrics_reports_nothing(tmp_path: Path) -> None:
    module = _load_module()
    module.REPO_ROOT = tmp_path
    (tmp_path / "src" / "automedia" / "pipelines").mkdir(parents=True)
    (tmp_path / "src" / "automedia" / "pipelines" / "runner.py").write_text(
        "x = 1\n" * 100, encoding="utf-8"
    )
    fresh_rfc = tmp_path / "docs" / "dev" / "deep-module-rfc-999.md"
    fresh_rfc.parent.mkdir(parents=True)
    fresh_rfc.write_text(
        "**Status:** Proposed\n**Date:** 2026-10-23\n100 lines runner.py\n",
        encoding="utf-8",
    )
    assert module.propose_aging_findings(proposed_max_age_days=9_000) == []


def test_stale_metrics_are_reported() -> None:
    module = _load_module()
    findings = module.propose_aging_findings(proposed_max_age_days=0)
    assert any("recorded runner.py" in finding for finding in findings)


def test_parse_status_and_date() -> None:
    module = _load_module()
    text = (REPO_ROOT / "docs" / "dev" / "deep-module-rfc-001.md").read_text(encoding="utf-8")
    assert module._parse_status(text) == "Proposed"
    assert module._parse_date(text) is not None
