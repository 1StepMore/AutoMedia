#!/usr/bin/env python3
"""Regression check for issue #335: copy gates must skip the no-article placeholder.

``qa_only`` injects ``[content skipped in qa_only mode]`` as ``content`` because
no gate produces an article.  G2 reviewed that marker as prose and failed the
journey on checks (tone/evidence/specificity) that cannot apply.  G2 and G3
must return ``status="skipped"`` for the marker instead.

Exits 0 and prints ``REG335_PLACEHOLDER_GATES_SKIPPED`` on success, else exits 1.
"""

from __future__ import annotations

import sys

from automedia.gates._context import CONTENT_PLACEHOLDER_PREFIX, GateContext
from automedia.gates.brand_cta import G3BrandCTA
from automedia.gates.copy_review import G2CopyReview

PLACEHOLDER = f"{CONTENT_PLACEHOLDER_PREFIX} qa_only mode]"


def main() -> int:
    context = GateContext(content=PLACEHOLDER, brand_profile={"brand_name": "my-brand"})
    for gate_name, gate in (("G2", G2CopyReview()), ("G3", G3BrandCTA())):
        result = gate.execute(context)
        if result.get("status") != "skipped":
            print(f"REG335_FAILED: {gate_name} did not skip the placeholder: {result}")
            return 1
        if result.get("passed") is not True:
            print(f"REG335_FAILED: {gate_name} skip was not passing: {result}")
            return 1
    print("REG335_PLACEHOLDER_GATES_SKIPPED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
