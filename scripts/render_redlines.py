#!/usr/bin/env python3
"""Render governance/redlines.yaml -> docs/dev/redlines.md.

MANUAL-ONLY regeneration, CI-CHECKED drift (same pattern as doc_inventory.py).
Usage:
    python scripts/render_redlines.py            # write
    python scripts/render_redlines.py --check    # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "src" / "automedia" / "governance" / "redlines.yaml"
OUTPUT = REPO_ROOT / "docs" / "dev" / "redlines.md"

HEADER = """<!-- AUTO-GENERATED from src/automedia/governance/redlines.yaml -->
<!-- Do not edit by hand. Regenerate: python scripts/render_redlines.py -->

# Agent Red Lines

This file is the **distribution format** for agent red lines. The source of
truth is `src/automedia/governance/redlines.yaml`, which is a compiler input —
harnesses read this Markdown, never the YAML.

| ID | Constraint |
|---|---|
"""


def render() -> str:
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    rows = [f"| `{r['id']}` | {r['text']} |" for r in doc["redlines"]]
    return HEADER + "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only")
    args = parser.parse_args(argv)

    generated = render()
    if args.check:
        if not OUTPUT.is_file():
            print(f"FAIL: {OUTPUT.relative_to(REPO_ROOT).as_posix()} missing")
            return 1
        committed = OUTPUT.read_text(encoding="utf-8")
        if committed != generated:
            print("FAIL: docs/dev/redlines.md drifted from redlines.yaml")
            print("      Regenerate: python scripts/render_redlines.py")
            return 1
        print("OK: redlines.md matches redlines.yaml")
        return 0

    OUTPUT.write_text(generated, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
