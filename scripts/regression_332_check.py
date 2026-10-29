#!/usr/bin/env python3
"""Regression check for issue #332: ASR availability must not lie.

Proves two things without needing ``faster-whisper`` installed:

1. ``pyproject.toml`` keeps the ``asr-faster`` extra below ``av`` 19, the
   release that dropped the ``metadata_errors`` kwarg faster-whisper still
   passes to ``av.open``.
2. ``FasterWhisperASREngine.check_available()`` performs a real decode probe,
   so an installed-but-incompatible combination reports unavailable instead
   of claiming to be ready and failing during transcription.

Exits 0 and prints ``REG332_ASR_PROBE_GUARDED`` on success, else exits 1.
"""

from __future__ import annotations

import sys
import tomllib
import types
from pathlib import Path

from automedia.engines.implementations.asr_faster_whisper import FasterWhisperASREngine


def _check_pin() -> str | None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    requirements = data["project"]["optional-dependencies"]["asr-faster"]
    matching = [req for req in requirements if req.replace(" ", "").startswith("av<19")]
    if not matching:
        return f"asr-faster does not pin av<19: {requirements!r}"
    return None


def _check_probe() -> str | None:
    module = types.ModuleType("faster_whisper")

    def _incompatible(_audio: object) -> None:
        raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")

    module.decode_audio = _incompatible  # type: ignore[attr-defined]
    original = sys.modules.get("faster_whisper")
    sys.modules["faster_whisper"] = module
    try:
        available, message = FasterWhisperASREngine({}).check_available()
    finally:
        if original is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = original
    if available:
        return "check_available reported an incompatible av as available"
    if "cannot decode audio" not in message:
        return f"unexpected message: {message!r}"
    return None


def main() -> int:
    for problem in (_check_pin(), _check_probe()):
        if problem is not None:
            print(f"REG332_FAILED: {problem}")
            return 1
    print("REG332_ASR_PROBE_GUARDED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
