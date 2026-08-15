"""Tests for G0 fact-check Chinese support — bidirectional number
verification, Chinese date parsing, and the normalization helper.

Covers issue #62: containment-only number checks missed contradictions
("市场规模达87.2亿" vs source 82.7) and Chinese dates were invisible to
the timeline check.
"""

from __future__ import annotations

from typing import Any

from automedia.gates.fact_check import (
    G0FactCheck,
    _check_number_verification,
    _check_timeline,
    _normalize_number,
)


def _run_gate(content: str, source_data: dict[str, Any]) -> dict[str, Any]:
    """Execute the gate with the deterministic path (no LLM)."""
    return G0FactCheck().execute(
        {
            "content": content,
            "source_data": source_data,
            "config": {"enable_llm": False},
        }
    )


def _number_check(content: str, key_numbers: dict[str, str]) -> dict[str, Any]:
    """Run only the number_verification check."""
    return _check_number_verification(content, {"key_numbers": key_numbers})


def _timeline_check(content: str, published_date: str) -> dict[str, Any]:
    """Run only the timeline check."""
    return _check_timeline(content, {"published_date": published_date})


# =========================================================================
# _normalize_number
# =========================================================================


class TestNormalizeNumber:
    """Module-level normalization helper strips qualifiers/units/separators."""

    def test_plain_integer_and_decimal(self) -> None:
        assert _normalize_number("42") == 42.0
        assert _normalize_number("82.7") == 82.7

    def test_strips_qualifiers(self) -> None:
        assert _normalize_number("约82.7") == 82.7
        assert _normalize_number("大约82.7") == 82.7
        assert _normalize_number("近82.7") == 82.7
        assert _normalize_number("达82.7") == 82.7
        assert _normalize_number("达到82.7") == 82.7
        assert _normalize_number("超过82.7") == 82.7

    def test_strips_unit_suffixes(self) -> None:
        assert _normalize_number("87.2亿") == 87.2
        assert _normalize_number("82.7万") == 82.7
        assert _normalize_number("87.2亿元") == 87.2
        assert _normalize_number("82.7万元") == 82.7
        assert _normalize_number("12%") == 12.0
        assert _normalize_number("12％") == 12.0
        assert _normalize_number("87.2美元") == 87.2
        assert _normalize_number("87.2亿美元") == 87.2
        assert _normalize_number("50人") == 50.0
        assert _normalize_number("20家") == 20.0
        assert _normalize_number("3个") == 3.0
        assert _normalize_number("5台") == 5.0

    def test_strips_thousands_separators(self) -> None:
        assert _normalize_number("8,200元") == 8200.0
        assert _normalize_number("1,234,567") == 1234567.0
        assert _normalize_number("1,234.5") == 1234.5

    def test_magnitude_conversion_intentionally_not_applied(self) -> None:
        # Documented limitation: 亿/万 are stripped, never multiplied.
        assert _normalize_number("87.2亿") == _normalize_number("87.2")
        assert _normalize_number("82.7万") == _normalize_number("82.7")

    def test_qualifier_units_and_separators_combined(self) -> None:
        assert _normalize_number("达到1,234.5万元") == 1234.5
        assert _normalize_number("约87.2亿美元") == 87.2

    def test_invalid_input_returns_none(self) -> None:
        assert _normalize_number("") is None
        assert _normalize_number("   ") is None
        assert _normalize_number("abc") is None
        assert _normalize_number("42 million") is None
        assert _normalize_number("82.7元abc") is None


# =========================================================================
# Bidirectional number verification
# =========================================================================


class TestNumberVerificationBidirectional:
    """Reverse direction: numbers adjacent to a label must agree with source."""

    def test_contradiction_near_label_fails(self) -> None:
        """Content "市场规模达87.2亿元" contradicts source market_size=82.7."""
        result = _number_check("市场规模达87.2亿元", {"market_size": "82.7"})
        assert result["passed"] is False
        detail = result["detail"]
        assert "87.2" in detail  # content number named
        assert "82.7" in detail  # source number named

    def test_defect_scenario_both_values_present_fails(self) -> None:
        """87.2 near the label is caught even though 82.7 appears elsewhere."""
        content = "市场规模达87.2亿元，公司此前称82.7亿"
        result = _number_check(content, {"market_size": "82.7"})
        assert result["passed"] is False
        assert "87.2" in result["detail"]
        assert "82.7" in result["detail"]

    def test_matching_value_with_qualifier_passes(self) -> None:
        """Label-proximity check tolerates qualifiers and unit suffixes."""
        content = "市场规模达82.7亿元，增长约12%"
        result = _number_check(
            content,
            {"market_size": "82.7", "growth_rate": "12"},
        )
        assert result["passed"] is True

    def test_unrelated_numbers_untouched(self) -> None:
        """A figure with no label near it is never inspected."""
        result = _number_check("82.7亿元规模，团队有50人", {"market_size": "82.7"})
        assert result["passed"] is True

    def test_forward_containment_still_enforced(self) -> None:
        """Source value missing from content still fails."""
        result = _number_check("市场规模持续扩大，前景广阔", {"market_size": "82.7"})
        assert result["passed"] is False
        assert "not found in content" in result["detail"]

    def test_forward_normalized_match_passes(self) -> None:
        """Source "8200" matches content "8,200万元" (separator tolerance)."""
        result = _number_check("市场规模达8,200万元", {"market_size": "8200"})
        assert result["passed"] is True

    def test_english_label_gloss_fires_on_chinese_content(self) -> None:
        """English source label market_size maps to 规模/市场规模 gloss."""
        result = _number_check("市场规模达87.2亿元", {"market_size": "82.7"})
        assert result["passed"] is False
        assert "market_size" in result["detail"]

    def test_chinese_label_matches_directly(self) -> None:
        """A Chinese source label is itself a label candidate."""
        result = _number_check("市场规模达87.2亿元", {"市场规模": "82.7"})
        assert result["passed"] is False
        assert "市场规模" in result["detail"]

    def test_number_on_left_of_label_fails(self) -> None:
        """Phrase before the label is checked too (87.2亿规模)."""
        result = _number_check("87.2亿元规模", {"market_size": "82.7"})
        assert result["passed"] is False
        assert "87.2" in result["detail"]

    def test_matching_number_on_left_of_label_passes(self) -> None:
        result = _number_check("82.7亿元规模", {"market_size": "82.7"})
        assert result["passed"] is True

    def test_multiple_occurrences_one_bad_fails(self) -> None:
        """Each label occurrence is checked; one bad value fails the gate."""
        result = _number_check("价格50元起，价格达80元", {"price": "50"})
        assert result["passed"] is False
        assert "80" in result["detail"]

    def test_multiple_numbers_in_one_phrase_fail_on_each_differing(self) -> None:
        """Every windowed number differing from source is reported."""
        result = _number_check("市场规模达87.2亿至82.7亿元", {"market_size": "82.7"})
        assert result["passed"] is False
        assert "87.2" in result["detail"]

    def test_repeat_gloss_matches_deduplicated(self) -> None:
        """规模 and 市场规模 both hit the same phrase — one detail only."""
        result = _number_check("市场规模达87.2亿元", {"market_size": "82.7"})
        assert result["detail"].count("contradicts source value") == 1

    def test_gloss_label_inside_number_phrase_passes(self) -> None:
        """增长 gloss: "增长约12%" normalizes to 12 == source 12."""
        result = _number_check("增长约12%", {"growth_rate": "12"})
        assert result["passed"] is True

    def test_gloss_rate_ambiguous_word_not_flagged(self) -> None:
        """率 inside unrelated words (效率) produces no number phrase."""
        result = _number_check("团队效率大幅提升", {"rate": "12"})
        assert result["passed"] is False  # forward containment still fails
        assert "not found in content" in result["detail"]

    def test_non_numeric_expected_skips_reverse_compare(self) -> None:
        """Unparseable expected value ("42 million") skips numeric reverse check."""
        result = _number_check("Revenue was 42 million this year.", {"revenue": "42 million"})
        assert result["passed"] is True

    def test_empty_key_numbers_passes(self) -> None:
        result = _number_check("任何内容", {})
        assert result["passed"] is True
        assert "no key_numbers" in result["detail"]

    def test_gate_level_contradiction_fails(self) -> None:
        """Full gate run reports number_verification failed."""
        result = _run_gate(
            "市场规模达87.2亿元",
            {
                "url": "",
                "published_date": "",
                "key_numbers": {"market_size": "82.7"},
                "entities": [],
                "quotes": [],
            },
        )
        assert result["passed"] is False
        num = next(c for c in result["checks"] if c["name"] == "number_verification")
        assert num["passed"] is False


# =========================================================================
# Timeline — Chinese dates
# =========================================================================


class TestTimelineChineseDates:
    """Chinese date forms ("X月X日", "X年X月X日", "X年X月") are parsed."""

    def test_month_day_before_pub_passes(self) -> None:
        result = _timeline_check("公司将于7月31日发布财报", "2026-08-15")
        assert result["passed"] is True

    def test_month_day_after_pub_fails(self) -> None:
        result = _timeline_check("公司将于8月20日发布财报", "2026-08-15")
        assert result["passed"] is False
        assert "2026-08-20" in result["detail"]

    def test_full_chinese_date_after_pub_fails(self) -> None:
        result = _timeline_check("公司将于2026年8月20日发布财报", "2026-08-15")
        assert result["passed"] is False
        assert "2026-08-20" in result["detail"]

    def test_full_chinese_date_before_pub_passes(self) -> None:
        result = _timeline_check("公司已于2026年7月20日发布财报", "2026-08-15")
        assert result["passed"] is True

    def test_year_month_after_pub_fails(self) -> None:
        result = _timeline_check("2026年9月发布", "2026-08-15")
        assert result["passed"] is False
        assert "2026-09-01" in result["detail"]

    def test_year_month_before_pub_passes(self) -> None:
        result = _timeline_check("2026年7月发布", "2026-08-15")
        assert result["passed"] is True

    def test_rollover_december_to_previous_year_passes(self) -> None:
        """12月31日 in a January article refers to the previous December."""
        result = _timeline_check("去年12月31日", "2026-01-05")
        assert result["passed"] is True

    def test_same_year_future_fails(self) -> None:
        """2月1日 vs published 2026-01-05 stays in the same year and fails."""
        result = _timeline_check("2月1日", "2026-01-05")
        assert result["passed"] is False
        assert "2026-02-01" in result["detail"]

    def test_rollover_threshold_boundary_no_rollover(self) -> None:
        """From February, December is only 10 months ahead — no rollover."""
        result = _timeline_check("12月31日", "2026-02-01")
        assert result["passed"] is False  # 2026-12-31 is a future date

    def test_iso_regression_future_fails(self) -> None:
        result = _timeline_check("Event on 2025-12-31 was significant.", "2024-01-01")
        assert result["passed"] is False

    def test_iso_regression_past_passes(self) -> None:
        result = _timeline_check("Event on 2023-06-15 was significant.", "2024-01-01")
        assert result["passed"] is True

    def test_mixed_iso_and_chinese_lists_all_offending_dates(self) -> None:
        result = _timeline_check("8月20日与2026-09-01", "2026-08-15")
        assert result["passed"] is False
        assert "2026-08-20" in result["detail"]
        assert "2026-09-01" in result["detail"]

    def test_full_and_bare_chinese_dates_deduplicated(self) -> None:
        """2026年8月20日 and 8月20日 are the same date — listed once."""
        result = _timeline_check("2026年8月20日与8月20日", "2026-08-15")
        assert result["passed"] is False
        assert result["detail"].count("2026-08-20") == 1

    def test_unparseable_published_date_passes(self) -> None:
        result = _timeline_check("8月20日", "not-a-date")
        assert result["passed"] is True
        assert "cannot parse" in result["detail"]

    def test_no_published_date_passes(self) -> None:
        result = _timeline_check("8月20日", "")
        assert result["passed"] is True
        assert "no published_date" in result["detail"]

    def test_aware_published_date_compares_without_crash(self) -> None:
        """ISO-with-Z published_date must not crash the naive-date comparison."""
        result = _timeline_check("8月20日", "2026-08-15T00:00:00Z")
        assert result["passed"] is False
        assert "2026-08-20" in result["detail"]

    def test_gate_level_chinese_date_fails(self) -> None:
        result = _run_gate(
            "公司将于2026年8月20日发布财报",
            {
                "url": "",
                "published_date": "2026-08-15",
                "key_numbers": {},
                "entities": [],
                "quotes": [],
            },
        )
        assert result["passed"] is False
        tl = next(c for c in result["checks"] if c["name"] == "timeline")
        assert tl["passed"] is False
        assert "2026-08-20" in tl["detail"]
