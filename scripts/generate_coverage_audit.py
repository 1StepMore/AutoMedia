#!/usr/bin/env python3
"""Regenerate scenarios/baseline/coverage-audit.json.

MANUAL-ONLY regeneration, CI-CHECKED drift (same pattern as doc_inventory.py).
The committed artifact carries ``generated_at: ""`` by convention and ends
WITHOUT a trailing newline; pass --blank-generated-at to reproduce it
byte-for-byte.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from automedia.validation.coverage import coverage_audit

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "scenarios" / "baseline" / "coverage-audit.json"


def render(blank_generated_at: bool) -> str:
    data = coverage_audit()
    if blank_generated_at:
        data["generated_at"] = ""
    return json.dumps(data, indent=2, ensure_ascii=False)  # no trailing \n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--blank-generated-at", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        # The committed artifact carries generated_at="". Render THAT shape,
        # not the live timestamp -- otherwise --check is red on every run.
        rendered = render(blank_generated_at=True)
        if not args.output.is_file():
            print(f"GOV401 coverage-audit missing: {args.output}")
            return 1
        if args.output.read_text(encoding="utf-8") != rendered:
            print("GOV401 coverage-audit.json drifted from a fresh audit")
            print(
                "      Regenerate: python scripts/generate_coverage_audit.py --blank-generated-at"
            )
            return 1
        print("OK: coverage-audit.json matches a fresh audit")
        return 0

    rendered = render(args.blank_generated_at)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
