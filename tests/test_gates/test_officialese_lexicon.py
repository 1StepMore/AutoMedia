"""One definition for the CN officialese word list (#442)."""

from __future__ import annotations

import json
from pathlib import Path

from automedia.gates.failure_modes import FAILURE_MODES
from automedia.gates.lexicon import CN_OFFICIALESE_RE, CN_OFFICIALESE_WORDS


def test_word_list_is_defined_once() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "automedia"
    hits = sorted(p.name for p in root.rglob("*.py") if "闭环" in p.read_text(encoding="utf-8"))
    assert hits == ["lexicon.py"]


def test_detector_uses_the_shared_patterns() -> None:
    assert CN_OFFICIALESE_RE.search("形成闭环")
    assert CN_OFFICIALESE_RE.search("生态")
    assert not CN_OFFICIALESE_RE.search("生态系统")


def test_failure_modes_names_every_shared_word() -> None:
    text = json.dumps(FAILURE_MODES["G1"], ensure_ascii=False)
    assert all(word in text for word in CN_OFFICIALESE_WORDS)
