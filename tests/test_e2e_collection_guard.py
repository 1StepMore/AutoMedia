"""Guard against the e2e suite being silently deselected."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_e2e_suite_collects_tests() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_e2e",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    match = re.search(r"(\d+) tests? collected", proc.stdout)
    assert match is not None, proc.stdout
    assert int(match.group(1)) > 0, proc.stdout


def test_makefile_e2e_target_clears_default_addopts() -> None:
    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^test-e2e:\n((?:\t.*\n)+)", makefile, re.MULTILINE)
    assert match is not None, "Makefile is missing the test-e2e target"
    recipe = match.group(1)
    assert "-o addopts=" in recipe, recipe
    assert "pytest tests/test_e2e/" in recipe, recipe
