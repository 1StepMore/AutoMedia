#!/usr/bin/env python3
"""Regression check for issue #496: emoji never reach the captions and a scene
without a measured duration never loses its words.

The TTS service read the closing ``👇`` as「反手十指向下指」, and the SRT wrapper
skipped a scene whose duration was not positive, so ``narration.srt`` ended on a
fragment while the audio still spoke the full closing sentence.

Exits 0 and prints ``REG496_NARRATION_EMOJI_SRT_GUARDED`` on success.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from automedia.pipelines.audio_pipeline import AudioPipeline


def _spoken_lines(body: str) -> str:
    return "".join(
        line
        for line in body.splitlines()
        if line.strip() and not line.strip().isdigit() and "-->" not in line
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reg496-") as raw:
        out = Path(raw) / "narration.srt"
        AudioPipeline().generate_srt_from_scenes(
            [
                {"text": "排期表几天没更新了？", "start": 0.0, "duration": 2.0},
                {"text": "评论区聊聊👇", "start": 2.0, "duration": 0.0},
            ],
            str(out),
        )
        body = out.read_text(encoding="utf-8") if out.is_file() else ""

    words = _spoken_lines(body)
    if "👇" in body:
        print(f"REG496_FAILED: emoji leaked into the captions: {words!r}")
        return 1
    if "评论区聊聊" not in words:
        print(f"REG496_FAILED: zero-duration closing scene lost: {words!r}")
        return 1
    print("REG496_NARRATION_EMOJI_SRT_GUARDED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
