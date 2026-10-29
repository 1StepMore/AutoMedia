#!/usr/bin/env python3
"""Regression check for issue #336: subtitle assertions must read the words.

Structural checks (cue count, timing) passed a subtitle full of ASR
substitutions.  ``text_similarity`` compares the produced text with the script
that was narrated, so a garbled transcript fails even when its timing is valid.

Exits 0 and prints ``REG336_TEXT_FIDELITY_GUARDED`` on success.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from automedia.validation.expects import evaluate_expect
from automedia.validation.schema import Expect

SCRIPT = "别只盯着短视频，播客才是品牌影响力的慢变量。戴耳机通勤时，声音最贴身。"
FAITHFUL = (
    "1\n00:00:00,000 --> 00:00:02,000\n"
    "别只盯着短视频，播客才是品牌影响力的慢变量\n\n"
    "2\n00:00:02,000 --> 00:00:04,000\n戴耳机通勤时，声音最贴身\n"
)
GARBLED = (
    "1\n00:00:00,000 --> 00:00:02,000\n太别指定者短视评播课才是评牌影响力的慢编量\n\n"
    "2\n00:00:02,000 --> 00:00:04,000\n戴耳机通勤时，声音最贴身\n"
)


def _grade(directory: Path, subtitle: str) -> bool:
    (directory / "script.md").write_text(SCRIPT, encoding="utf-8")
    (directory / "narration.srt").write_text(subtitle, encoding="utf-8")
    expect = Expect.from_dict(
        {
            "artifact_exists": "narration.srt",
            "text_similarity": {"reference": "script.md", "min_ratio": 0.8},
        }
    )
    return evaluate_expect(expect, {"success": True}, cwd=directory).passed


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reg336-") as raw:
        directory = Path(raw)
        if not _grade(directory, FAITHFUL):
            print("REG336_FAILED: a faithful transcript did not pass")
            return 1
        if _grade(directory, GARBLED):
            print("REG336_FAILED: a garbled transcript passed")
            return 1
    print("REG336_TEXT_FIDELITY_GUARDED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
