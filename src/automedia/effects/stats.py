"""Pure computation functions for content analytics.

All functions in this module are stateless and operate solely on
text content or structured gate context.  No side effects.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# word_count
# ---------------------------------------------------------------------------


def word_count(text: str) -> dict[str, Any]:
    """Count words, characters, and sentences in *text*.

    Parameters
    ----------
    text:
        The content text to analyse.

    Returns
    -------
    dict
        ``{"word_count": int, "char_count": int,
           "char_count_no_spaces": int, "sentence_count": int,
           "avg_words_per_sentence": float}``
    """
    cleaned = re.sub(r"\s+", " ", text).strip()

    words = cleaned.split() if cleaned else []
    chars = len(text)
    chars_no_spaces = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))

    # Sentence splitting: . ! ? followed by space or end-of-string
    sentences = re.split(r"[.!?]+(?:\s|$)", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = max(len(sentences), 1) if words else 1

    return {
        "word_count": len(words),
        "char_count": chars,
        "char_count_no_spaces": chars_no_spaces,
        "sentence_count": sentence_count,
        "avg_words_per_sentence": round(len(words) / sentence_count, 2) if words else 0.0,
    }


# ---------------------------------------------------------------------------
# sentiment_score
# ---------------------------------------------------------------------------

_POSITIVE_WORDS: frozenset[str] = frozenset({
    "good", "great", "excellent", "amazing", "wonderful", "fantastic",
    "outstanding", "brilliant", "awesome", "incredible", "best",
    "love", "beautiful", "perfect", "impressive", "superb",
    "remarkable", "exceptional", "terrific", "magnificent",
    "splendid", "marvelous", "stellar", "superior", "top-tier",
    "innovative", "powerful", "effective", "helpful", "valuable",
    "efficient", "reliable", "robust", "seamless", "intuitive",
    "user-friendly", "high-quality", "cutting-edge", "state-of-the-art",
    "breakthrough", "revolutionary", "game-changing",
    # Chinese positive
    "好", "优秀", "出色", "精彩", "棒", "厉害", "赞", "完美",
    "创新", "强大", "有效", "实用", "可靠", "出色", "优越",
    "一流", "顶尖", "突破", "革命性",
})

_NEGATIVE_WORDS: frozenset[str] = frozenset({
    "bad", "terrible", "awful", "horrible", "poor", "worst",
    "hate", "ugly", "disgusting", "dreadful", "atrocious",
    "abysmal", "mediocre", "inferior", "subpar", "lousy",
    "appalling", "horrendous", "shocking", "frustrating",
    "disappointing", "problematic", "broken", "failed", "failure",
    "buggy", "slow", "expensive", "difficult", "complicated",
    "confusing", "unreliable", "inefficient", "useless",
    "outdated", "obsolete", "clunky", "cumbersome",
    # Chinese negative
    "差", "糟糕", "可怕", "恶心", "劣质", "最差",
    "失败", "失望", "问题", "错误", "昂贵", "困难",
    "复杂", "混乱", "不可靠", "低效", "无用",
    "过时", "落后", "笨重",
})


def sentiment_score(text: str) -> dict[str, Any]:
    """Compute a simple keyword-based sentiment score.

    Uses built-in positive/negative word lists (English + Chinese).
    Returns a normalised score between ``-1.0`` (very negative) and
    ``+1.0`` (very positive).

    Parameters
    ----------
    text:
        The content text to analyse.

    Returns
    -------
    dict
        ``{"score": float, "label": str, "positive_words": int,
           "negative_words": int, "total_scored": int}``
    """
    lower = text.lower()
    words = re.findall(r"\w+", lower)

    pos_count = sum(1 for w in words if w in _POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in _NEGATIVE_WORDS)
    total = pos_count + neg_count

    if total == 0:
        return {
            "score": 0.0,
            "label": "neutral",
            "positive_words": 0,
            "negative_words": 0,
            "total_scored": 0,
        }

    raw_score = (pos_count - neg_count) / total
    score = round(raw_score, 4)

    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return {
        "score": score,
        "label": label,
        "positive_words": pos_count,
        "negative_words": neg_count,
        "total_scored": total,
    }


# ---------------------------------------------------------------------------
# readability_index
# ---------------------------------------------------------------------------


def _estimate_syllables(word: str) -> int:
    """Rough syllable count by counting vowel groups."""
    word = word.lower().strip(".,!?;:\"'()-")
    if not word:
        return 1
    vowel_groups = len(re.findall(r"[aeiouy]+", word))
    return max(vowel_groups, 1)


def readability_index(text: str) -> dict[str, Any]:
    """Approximate Flesch Reading Ease score for English text.

    Formula::

        FRE = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)

    Syllable count is estimated by counting vowel groups (rough heuristic).

    Parameters
    ----------
    text:
        The content text to analyse.

    Returns
    -------
    dict
        ``{"flesch_reading_ease": float, "grade_level": str,
           "avg_syllables_per_word": float, "avg_words_per_sentence": float}``
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    words = cleaned.split() if cleaned else []

    if not words:
        return {
            "flesch_reading_ease": 0.0,
            "grade_level": "N/A",
            "avg_syllables_per_word": 0.0,
            "avg_words_per_sentence": 0.0,
        }

    sentences = re.split(r"[.!?]+(?:\s|$)", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = max(len(sentences), 1)

    total_syllables = sum(_estimate_syllables(w) for w in words)
    total_words = len(words)

    avg_words_per_sentence = total_words / sentence_count
    avg_syllables_per_word = total_syllables / total_words

    # Flesch Reading Ease
    fre = 206.835 - 1.015 * avg_words_per_sentence - 84.6 * avg_syllables_per_word
    fre = max(0.0, min(100.0, fre))  # Clamp to [0, 100]

    # Grade level mapping
    if fre >= 90:
        grade = "Very Easy (5th grade)"
    elif fre >= 80:
        grade = "Easy (6th grade)"
    elif fre >= 70:
        grade = "Fairly Easy (7th grade)"
    elif fre >= 60:
        grade = "Standard (8th-9th grade)"
    elif fre >= 50:
        grade = "Fairly Difficult (10th-12th grade)"
    elif fre >= 30:
        grade = "Difficult (College)"
    else:
        grade = "Very Difficult (College Graduate)"

    return {
        "flesch_reading_ease": round(fre, 2),
        "grade_level": grade,
        "avg_syllables_per_word": round(avg_syllables_per_word, 2),
        "avg_words_per_sentence": round(avg_words_per_sentence, 2),
    }


# ---------------------------------------------------------------------------
# brand_mention_frequency
# ---------------------------------------------------------------------------


def brand_mention_frequency(text: str, brand_names: list[str]) -> dict[str, Any]:
    """Count how often each brand name appears in *text*.

    Case-insensitive matching.  Each brand name is counted independently
    even when brand names overlap.

    Parameters
    ----------
    text:
        The content text to analyse.
    brand_names:
        List of brand names to search for.

    Returns
    -------
    dict
        ``{"mentions": {brand: count, ...}, "total_mentions": int}``
    """
    lower_text = text.lower()
    mentions: dict[str, int] = {}
    total = 0

    for brand in brand_names:
        if not brand:
            continue
        pattern = re.escape(brand.lower())
        count = len(re.findall(pattern, lower_text))
        if count > 0:
            mentions[brand] = count
            total += count

    return {
        "mentions": mentions,
        "total_mentions": total,
    }


# ---------------------------------------------------------------------------
# seo_score_aggregation
# ---------------------------------------------------------------------------


def seo_score_aggregation(gate_context: dict[str, Any]) -> dict[str, Any]:
    """Aggregate SEO scores from gate context.

    Reads ``gate_context.get("extra", {}).get("seo_scores", [])`` which
    is expected to be a list of dicts each with a ``"score"`` key, or a
    flat list of numeric scores.

    Parameters
    ----------
    gate_context:
        The gate execution context containing ``extra["seo_scores"]``.

    Returns
    -------
    dict
        ``{"count": int, "average": float, "min": float, "max": float,
           "scores": [float, ...]}``
        or ``{"count": 0, "average": 0.0, "min": 0.0, "max": 0.0,
           "scores": []}`` when no scores are available.
    """
    extra = gate_context.get("extra", {}) or {}
    scores_raw = extra.get("seo_scores", []) or []

    if not isinstance(scores_raw, list) or not scores_raw:
        return {"count": 0, "average": 0.0, "min": 0.0, "max": 0.0, "scores": []}

    scores: list[float] = []
    for entry in scores_raw:
        if isinstance(entry, dict):
            s = entry.get("score")
            if isinstance(s, (int, float)):
                scores.append(float(s))
        elif isinstance(entry, (int, float)):
            scores.append(float(entry))

    if not scores:
        return {"count": 0, "average": 0.0, "min": 0.0, "max": 0.0, "scores": []}

    return {
        "count": len(scores),
        "average": round(sum(scores) / len(scores), 4),
        "min": min(scores),
        "max": max(scores),
        "scores": sorted(scores),
    }
