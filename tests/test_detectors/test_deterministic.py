"""Tests for DeterministicTasteDetector — the built-in, env-free detector.

The detector reuses the G1 humanizer's 9 check functions strictly by
import (no pattern duplication), so these tests pin the detector's
scoring contract with synthetic fixture strings only:

    ai_score = (# failing checks) / (# checks run)
    passed   = ai_score <= 0.5

The fixture strings below were validated against the real humanizer
patterns (including the #73 Chinese AI-taste additions): the CN
officialese text fails 5/9 checks, the clean CN text passes all 9, the
clean English text passes all 9, and the AI-marker English text fails
8/9 checks.
"""

from __future__ import annotations

import pytest

from automedia.detectors import (
    BaseDetector,
    DetectorRegistry,
    DeterministicTasteDetector,
    detect_text,
)
from automedia.gates.humanizer import _CHECK_NAMES

# ---------------------------------------------------------------------------
# Synthetic fixture strings (no production data)
# ---------------------------------------------------------------------------

_CLEAN_EN = "A quick brown fox jumps over the lazy dog. The sky is blue today."

_CLEAN_CN = "今天天气很好，我们去公园散步。晚上回家做饭，大家都很开心。"

# CN officialese (官腔黑话 + 空洞开头 + 绝对化表述) — real matches for
# _CN_ACADEMIC_RE (赋能/闭环/底层逻辑/生态), _HOLLOW_INTRO_RES (值得注意的是),
# _CN_FILLER_RE (综上所述), _TEMPLATE_CONCLUSION_RES (综上所述) and
# _ABSOLUTE_RE (所有人都/毫无疑问).
_CN_OFFICIALESE = (
    "综上所述，与此同时，我们必须推进产业赋能与闭环管理。"
    "值得注意的是，所有人都需要认识到，贯彻新发展理念势在必行。"
    "毫无疑问，我们必须落实底层逻辑，加强生态建设。"
)

# Heavy English AI markers — real matches for 8 of the 9 categories.
_AI_MARKER_EN = (
    "Furthermore, it is worth noting that we must leverage AI tools to "
    "utilize data effectively. "
    "In conclusion, everyone knows that automation always works and never "
    "fails and no one can deny and it is always reliable. "
    "Importantly, we must act now. "
    "It is worth noting that this matters. "
    "We must start today."
)

_GPTZERO_ENV = "AUTOMEDIA_DETECTOR_GPTZERO_API_KEY"


# =========================================================================
# Metadata & registration
# =========================================================================


class TestDeterministicTasteDetectorMetadata:
    """deterministic_taste has correct metadata and is always available."""

    def test_detector_name(self) -> None:
        """detector_name returns the class-level identifier."""
        assert DeterministicTasteDetector().detector_name == "deterministic_taste"

    def test_is_base_detector_subclass(self) -> None:
        """The detector implements the BaseDetector contract."""
        assert issubclass(DeterministicTasteDetector, BaseDetector)

    def test_env_required_empty_means_always_available(self) -> None:
        """Empty _env_required → available() is True without any env var."""
        det = DeterministicTasteDetector()
        assert det.env_required == ""
        assert det.available() is True

    def test_auto_registered_in_registry(self) -> None:
        """The detector is registered in the DetectorRegistry singleton."""
        assert "deterministic_taste" in DetectorRegistry()
        assert DetectorRegistry().get("deterministic_taste") is DeterministicTasteDetector

    def test_detector_name_is_read_only(self) -> None:
        """detector_name cannot be assigned on the instance."""
        det = DeterministicTasteDetector()
        with pytest.raises(AttributeError):
            det.detector_name = "mutated"

    def test_env_required_is_read_only(self) -> None:
        """env_required cannot be assigned on the instance."""
        det = DeterministicTasteDetector()
        with pytest.raises(AttributeError):
            det.env_required = "AUTOMEDIA_MUTATED"


# =========================================================================
# Scoring contract
# =========================================================================


class TestDeterministicTasteScoring:
    """ai_score is the failing/total ratio and passed = ai_score <= 0.5."""

    def test_clean_english_passes(self) -> None:
        """Clean English text scores 0.0 and passes."""
        result = DeterministicTasteDetector().detect(_CLEAN_EN)
        assert result["ai_score"] == 0.0
        assert result["passed"] is True
        assert result["name"] == "deterministic_taste"

    def test_clean_chinese_passes(self) -> None:
        """Plain Chinese text (no AI-taste markers) scores 0.0 and passes."""
        result = DeterministicTasteDetector().detect(_CLEAN_CN)
        assert result["ai_score"] == 0.0
        assert result["passed"] is True

    def test_cn_officialese_fails(self) -> None:
        """CN officialese text is honestly scored as AI-written (ai_score > 0.5)."""
        result = DeterministicTasteDetector().detect(_CN_OFFICIALESE)
        assert result["ai_score"] > 0.5
        assert result["passed"] is False

    def test_heavy_english_ai_markers_fail(self) -> None:
        """Heavy English AI-marker text is scored as AI-written (ai_score > 0.5)."""
        result = DeterministicTasteDetector().detect(_AI_MARKER_EN)
        assert result["ai_score"] > 0.5
        assert result["passed"] is False

    def test_ai_score_is_failing_ratio(self) -> None:
        """ai_score equals failing count divided by total checks run."""
        result = DeterministicTasteDetector().detect(_CN_OFFICIALESE)
        failing = [c for c in result["checks"] if not c["passed"]]
        assert result["ai_score"] == pytest.approx(len(failing) / len(result["checks"]))

    def test_check_count_derived_from_humanizer(self) -> None:
        """The check count is derived from the humanizer inventory, never hardcoded."""
        result = DeterministicTasteDetector().detect(_CLEAN_EN)
        assert len(result["checks"]) == len(_CHECK_NAMES)
        assert [c["name"] for c in result["checks"]] == _CHECK_NAMES


# =========================================================================
# Result structure & edge cases
# =========================================================================


class TestDeterministicTasteResultStructure:
    """DetectorResult carries the required keys and per-check details."""

    def test_result_has_all_required_keys(self) -> None:
        """Result contains name, ai_score, passed, detail, method, checks."""
        result = DeterministicTasteDetector().detect(_CLEAN_EN)
        assert set(result) == {"name", "ai_score", "passed", "detail", "method", "checks"}
        assert isinstance(result["ai_score"], float)
        assert isinstance(result["passed"], bool)
        assert isinstance(result["detail"], str)
        assert result["method"] == "deterministic"

    def test_checks_have_correct_structure(self) -> None:
        """Each per-check entry has name/passed/detail and mirrors humanizer output."""
        result = DeterministicTasteDetector().detect(_CN_OFFICIALESE)
        for check in result["checks"]:
            assert set(check) == {"name", "passed", "detail"}
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)
        failing = [c for c in result["checks"] if not c["passed"]]
        names = {c["name"] for c in failing}
        assert {
            "hollow_intros",
            "filler_connectors",
            "template_conclusions",
            "overacademic_vocabulary",
            "absolute_assertions",
        } <= names

    def test_detail_mentions_failing_checks(self) -> None:
        """detail is a human summary naming the failing check categories."""
        result = DeterministicTasteDetector().detect(_CN_OFFICIALESE)
        assert "hollow_intros" in result["detail"]
        assert "overacademic_vocabulary" in result["detail"]

    def test_empty_input_scores_zero(self) -> None:
        """Empty string → ai_score 0.0, passed True, detail 'empty input'."""
        result = DeterministicTasteDetector().detect("")
        assert result["ai_score"] == 0.0
        assert result["passed"] is True
        assert result["detail"] == "empty input"
        assert result["checks"] == []

    def test_whitespace_only_input_scores_zero(self) -> None:
        """Whitespace-only input is handled like empty input."""
        result = DeterministicTasteDetector().detect("   \n\t  ")
        assert result["ai_score"] == 0.0
        assert result["passed"] is True
        assert result["detail"] == "empty input"


# =========================================================================
# Convenience API
# =========================================================================


class TestDetectTextConvenience:
    """detect_text runs every available detector and returns its results."""

    def test_detect_text_runs_available_detectors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With the env-gated adapter unavailable, only deterministic_taste runs."""
        monkeypatch.delenv(_GPTZERO_ENV, raising=False)
        results = detect_text(_CLEAN_EN)
        assert len(results) == 1
        assert results[0]["name"] == "deterministic_taste"
        assert results[0]["passed"] is True

    def test_detect_text_reports_cn_officialese(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect_text propagates the AI-written verdict for CN officialese."""
        monkeypatch.delenv(_GPTZERO_ENV, raising=False)
        results = detect_text(_CN_OFFICIALESE)
        assert results[0]["ai_score"] > 0.5
        assert results[0]["passed"] is False
