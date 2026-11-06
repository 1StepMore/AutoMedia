#!/usr/bin/env python3
"""OS-independence gate: generated artifacts and write paths.

Three checks, one implementation shared by CI and pre-commit:

  1. Generated artifacts must not carry drive letters, /mnt/, /home/,
     /Users/, UNC prefixes, CR, or a BOM.
  2. ``write_text`` on a committed artifact must pin ``newline="\\n"``
     (Windows defaults to CRLF -- see governance-remediation-plan.md §B3).
  3. Ratchet: the repo-wide count of ``write_text`` calls WITHOUT
     ``newline=`` may not grow above the baseline.

Exit 0 = clean. Any finding = exit 1 with a GOV-code line.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Artifacts whose bytes are compared across platforms.
GENERATED_ARTIFACTS: tuple[str, ...] = (
    "docs/doc-inventory.md",
    "docs/dev/redlines.md",
    "scenarios/baseline/coverage-audit.json",
    "scenarios/baseline/threshold-snapshot.json",
)

# Committed artifacts whose writer must pin newline="\n".
ARTIFACT_WRITERS: tuple[str, ...] = (
    "scripts/doc_inventory.py",
    "scripts/snapshot_scenario_thresholds.py",
    "scripts/generate_coverage_audit.py",
    "scripts/render_redlines.py",
)

# Ratchet baseline. Lower it as writers are fixed; never raise it.
# 35 was the pre-B3 count. B3-4 (doc_inventory.py:223) and B3-5
# (snapshot_scenario_thresholds.py:137) fix 2 of them, so by the time this
# gate lands the repo is at 33. B1-4/B3-3 add NEW writers that already pin
# newline="\n" and are not counted. Setting 35 here would leave 2 slots of
# slack for regressions.
BASELINE_MISSING_NEWLINE = 33

_ABS_PATH = re.compile(
    r"(?<![A-Za-z0-9])"  # not part of a word
    r"(?:"
    r"[A-Za-z]:[\\/]"  # drive letter
    r"|/(?:mnt|home|Users)/"  # POSIX absolute roots
    r"|\\\\[A-Za-z0-9_.-]+\\"  # UNC
    r")"
)


def _check_artifacts() -> list[str]:
    findings: list[str] = []
    for rel in GENERATED_ARTIFACTS:
        path = REPO_ROOT / rel
        if not path.is_file():
            findings.append(f"GOV601 generated artifact missing: {rel}")
            continue
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            findings.append(f"GOV602 BOM in generated artifact: {rel}")
        if b"\r" in raw:
            findings.append(f"GOV603 CR in generated artifact: {rel}")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"GOV604 generated artifact is not UTF-8: {rel}")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = _ABS_PATH.search(line)
            if match:
                findings.append(
                    f"GOV605 absolute path in generated artifact: "
                    f"{rel}:{lineno}: {match.group(0)!r}"
                )
    return findings


def _write_text_calls(path: Path) -> list[ast.Call]:
    """AST, not grep: 11 call sites span multiple lines, so a line match
    would keep flagging a correctly fixed call (newline= on line 2-4)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write_text"
    ]


def _iter_py(roots: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def check_write_text() -> tuple[list[str], int]:
    findings: list[str] = []

    # Committed-artifact writers: blocking, zero tolerance.
    for rel in ARTIFACT_WRITERS:
        path = REPO_ROOT / rel
        if not path.is_file():
            # Fail closed: a deleted writer is a coverage hole, not a pass.
            findings.append(f"GOV608 artifact writer missing: {rel}")
            continue
        for call in _write_text_calls(path):
            if not any(kw.arg == "newline" for kw in call.keywords):
                # PERF401 waived: the sibling GOV608 branch keeps this a loop
                findings.append(  # noqa: PERF401
                    f"GOV606 artifact writer without newline=: {rel}:{call.lineno}"
                )

    # Repo-wide ratchet.
    missing = 0
    for path in _iter_py(("src", "scripts")):
        for call in _write_text_calls(path):
            if not any(kw.arg == "newline" for kw in call.keywords):
                missing += 1
    if missing > BASELINE_MISSING_NEWLINE:
        findings.append(
            f"GOV607 write_text missing newline= grew: {missing} > {BASELINE_MISSING_NEWLINE}"
        )
    return findings, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    findings = _check_artifacts()
    wt_findings, missing = check_write_text()
    findings.extend(wt_findings)

    for finding in findings:
        print(finding)

    if args.verbose:
        print(
            f"[info] write_text without newline=: {missing} (baseline {BASELINE_MISSING_NEWLINE})"
        )

    if findings:
        print(f"FAIL: {len(findings)} OS-independence finding(s)")
        return 1
    print(f"OK: OS-independence clean (write_text baseline {missing})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
