"""Offline keyword extraction — V3's honest producer (#471).

No LLM, no new dependencies: Chinese has no shipped segmenter, so candidates
come from punctuation/whitespace slicing → CJK-run extraction → stopword
trimming → frequency ranking.  Two vocabularies come out of one extractor:

- both sides use the **same** rule (phrases + in-phrase bigrams, frequency
  ordered) so the gate's set operations compare like with like.

The extraction is deliberately mechanical.  When its quality cannot separate
an off-topic draft from an on-topic one, that limitation is reported (see the
#471 卡住条款) — the gate's criteria are never loosened to compensate.
"""

from __future__ import annotations

import re
from collections import Counter

#: CJK ideograph runs — the only script this extractor keywords.
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")

#: Function characters that split a CJK run into phrases (虚词/结构字).
_STOPWORD_CHARS = frozenset(
    "的了呢吗吧呀啊哦嘛么把将被对从和与或也就都还更最很太再于是我在你他她它们这那哪个每某之其等"
)

#: A phrase shorter than this is not a usable keyword.
_MIN_PHRASE_LEN = 2

#: Upper bound on returned keywords per side.
_DEFAULT_MAX_KEYWORDS = 40


def _split_phrases(text: str) -> list[str]:
    """Slice *text* into CJK phrases: punctuation → runs → stopword chars."""
    phrases: list[str] = []
    for run in _CJK_RUN_RE.findall(text):
        phrase = ""
        for char in run:
            if char in _STOPWORD_CHARS:
                if len(phrase) >= _MIN_PHRASE_LEN:
                    phrases.append(phrase)
                phrase = ""
            else:
                phrase += char
        if len(phrase) >= _MIN_PHRASE_LEN:
            phrases.append(phrase)
    return phrases


def _grams_of(phrases: list[str]) -> list[str]:
    """Expand phrases into themselves plus in-phrase bigrams."""
    grams: list[str] = []
    for phrase in phrases:
        grams.append(phrase)
        grams.extend(phrase[i : i + 2] for i in range(len(phrase) - 1))
    return grams


def extract_source_keywords(text: str, *, max_keywords: int = _DEFAULT_MAX_KEYWORDS) -> list[str]:
    """Vocabulary for the source side (topic + source material).

    与内容侧同一套提取规则（短语 + 短语内 bigram，频次排序）——两侧词表
    可比，判据的集合运算才有意义。源侧不改写、不筛选：它就是判据的参照系。
    """
    grams = _grams_of(_split_phrases(text or ""))
    ordered = [gram for gram, _ in Counter(grams).most_common()]
    return ordered[:max_keywords]


def extract_content_keywords(text: str, *, max_keywords: int = _DEFAULT_MAX_KEYWORDS) -> list[str]:
    """Vocabulary for the content side — same rule as the source side."""
    grams = _grams_of(_split_phrases(text or ""))
    ordered = [gram for gram, _ in Counter(grams).most_common()]
    return ordered[:max_keywords]


__all__ = ["extract_content_keywords", "extract_source_keywords"]
