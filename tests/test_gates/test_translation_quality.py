"""Tests for L4TranslationQuality gate — OL translation output validation."""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates.base import BaseGate, _registry
from automedia.gates.translation_quality import (
    L4TranslationQuality,
    _CHECK_NAMES,
    _GARBLED_RE,
    _parse_frontmatter,
    GateResult,
)

# =========================================================================
# Shared test data
# =========================================================================

VALID_FRONTMATTER: str = """\
---
source_lang: en
target_lang: zh
---

Hello world! 你好世界！
"""

TRANS_WITHOUT_FRONTMATTER: str = "Hello world! 你好世界！"

MALFORMED_YAML: str = """\
---
source_lang: en
target_lang: [unclosed
---

Hello world!
"""

FRONTMATTER_MISSING_SOURCE: str = """\
---
target_lang: zh
---

Hello world!
"""

FRONTMATTER_MISSING_TARGET: str = """\
---
source_lang: en
---

Hello world!
"""


# =========================================================================
# Helpers
# =========================================================================


def _make_context(
    *,
    translated_md: str | None = None,
    source_lang: str = "en",
    target_lang: str = "zh",
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults.

    The translation_result is a dict (the most common production shape).
    """
    return {
        "translation_result": {
            "translated_md": translated_md
            if translated_md is not None
            else VALID_FRONTMATTER,
            "xliff_path": "/tmp/test.xliff",
            "warnings": [],
            "source_lang": source_lang,
            "target_lang": target_lang,
        },
        "source_lang": source_lang,
        "target_lang": target_lang,
    }


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestL4Metadata:
    """L4TranslationQuality has correct gate_name, failure_mode, etc."""

    def test_gate_name(self) -> None:
        gate = L4TranslationQuality()
        assert gate.gate_name == "L4"

    def test_failure_mode(self) -> None:
        gate = L4TranslationQuality()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(L4TranslationQuality, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "L4" in _registry
        assert _registry.get("L4") is L4TranslationQuality

    def test_check_names(self) -> None:
        assert L4TranslationQuality._check_names == _CHECK_NAMES


# =========================================================================
# Helper: _parse_frontmatter
# =========================================================================


class TestParseFrontmatter:
    """Unit tests for the frontmatter parser helper."""

    def test_valid_frontmatter(self) -> None:
        ok, data, err = _parse_frontmatter(VALID_FRONTMATTER)
        assert ok is True
        assert data is not None
        assert data["source_lang"] == "en"
        assert data["target_lang"] == "zh"
        assert err is None

    def test_no_frontmatter(self) -> None:
        ok, data, err = _parse_frontmatter(TRANS_WITHOUT_FRONTMATTER)
        assert ok is False
        assert data is None
        assert err is not None
        assert "No YAML frontmatter" in err

    def test_empty_string(self) -> None:
        ok, _data, err = _parse_frontmatter("")
        assert ok is False
        assert err is not None
        assert "No YAML frontmatter" in err

    def test_only_dashes(self) -> None:
        ok, _data, err = _parse_frontmatter("---\n---\ncontent")
        assert ok is False
        assert err is not None
        assert "empty" in err.lower()

    def test_malformed_yaml(self) -> None:
        ok, _data, err = _parse_frontmatter(MALFORMED_YAML)
        assert ok is False
        assert err is not None
        assert "Malformed YAML" in err

    def test_missing_closing_dashes(self) -> None:
        md = "---\nsource_lang: en\ntarget_lang: zh\ncontent here"
        ok, _data, err = _parse_frontmatter(md)
        assert ok is False
        assert err is not None
        assert "closing" in err

    def test_non_dict_yaml(self) -> None:
        md = "---\n- list\n- item\n---\ncontent"
        ok, _data, err = _parse_frontmatter(md)
        assert ok is False
        assert err is not None
        assert "not a mapping" in err

    def test_missing_source_lang(self) -> None:
        ok, _data, err = _parse_frontmatter(FRONTMATTER_MISSING_SOURCE)
        assert ok is False
        assert err is not None
        assert "source_lang" in err

    def test_missing_target_lang(self) -> None:
        ok, _data, err = _parse_frontmatter(FRONTMATTER_MISSING_TARGET)
        assert ok is False
        assert err is not None
        assert "target_lang" in err


# =========================================================================
# Frontmatter validation (via execute)
# =========================================================================


class TestFrontmatterValidation:
    """Full-gate frontmatter validation."""

    def test_valid_frontmatter_passes(self) -> None:
        ctx = _make_context()
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["frontmatter_valid"] is True

    def test_no_frontmatter_fails(self) -> None:
        ctx = _make_context(translated_md=TRANS_WITHOUT_FRONTMATTER)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["frontmatter_valid"] is False
        assert any("frontmatter" in f.lower() for f in result["failures"])

    def test_malformed_yaml_fails(self) -> None:
        ctx = _make_context(translated_md=MALFORMED_YAML)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["frontmatter_valid"] is False

    def test_missing_source_lang_fails(self) -> None:
        ctx = _make_context(translated_md=FRONTMATTER_MISSING_SOURCE)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["frontmatter_valid"] is False

    def test_missing_target_lang_fails(self) -> None:
        ctx = _make_context(translated_md=FRONTMATTER_MISSING_TARGET)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["frontmatter_valid"] is False


# =========================================================================
# Language match
# =========================================================================


class TestLanguageMatch:
    """Language matching checks."""

    def test_matching_languages_pass(self) -> None:
        ctx = _make_context(source_lang="en", target_lang="zh")
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["language_match"] is True

    def test_source_lang_mismatch_fails(self) -> None:
        ctx = _make_context(source_lang="fr", target_lang="zh")
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["language_match"] is False

    def test_target_lang_mismatch_fails(self) -> None:
        ctx = _make_context(source_lang="en", target_lang="ja")
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["language_match"] is False

    def test_both_lang_mismatch_fails(self) -> None:
        ctx = _make_context(source_lang="fr", target_lang="ja")
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["language_match"] is False

    def test_no_frontmatter_lang_match_fails(self) -> None:
        ctx = _make_context(
            translated_md=TRANS_WITHOUT_FRONTMATTER,
            source_lang="en",
            target_lang="zh",
        )
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["language_match"] is False
        assert any("frontmatter" in f.lower() for f in result["failures"])


# =========================================================================
# Garbled text detection
# =========================================================================


class TestGarbledTextDetection:
    """Garbled (replacement) character detection."""

    def test_clean_text_passes(self) -> None:
        ctx = _make_context()
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["no_garbled_text"] is True
        assert len(result["warnings"]) == 0

    def test_replacement_character_flagged(self) -> None:
        text = VALID_FRONTMATTER + "Some text with \ufffd replacement char."
        ctx = _make_context(translated_md=text)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["no_garbled_text"] is False
        assert len(result["warnings"]) > 0
        assert "Garbled" in result["warnings"][0]

    def test_control_characters_flagged(self) -> None:
        text = VALID_FRONTMATTER + "Text with \u0000 null char."
        ctx = _make_context(translated_md=text)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["no_garbled_text"] is False
        assert len(result["warnings"]) > 0

    def test_multiple_garbled_chars(self) -> None:
        text = VALID_FRONTMATTER + "\ufffd\ufffe\u0000"
        ctx = _make_context(translated_md=text)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["no_garbled_text"] is False
        assert len(result["warnings"]) >= 1

    @pytest.mark.parametrize(
        "char",
        ["\ufffd", "\ufffe", "\uffff", "\u0000", "\u0007", "\u001b"],
    )
    def test_each_garbled_char_detected(self, char: str) -> None:
        text = VALID_FRONTMATTER + f"garbled{char}end"
        ctx = _make_context(translated_md=text)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["no_garbled_text"] is False
        assert any("Garbled" in w for w in result["warnings"])


# =========================================================================
# Empty translation
# =========================================================================


class TestEmptyTranslation:
    """Non-empty translation checks."""

    def test_non_empty_passes(self) -> None:
        ctx = _make_context()
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["non_empty"] is True

    def test_empty_fails(self) -> None:
        ctx = _make_context(translated_md="")
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["non_empty"] is False
        assert any("empty" in f.lower() for f in result["failures"])

    def test_whitespace_only_fails(self) -> None:
        ctx = _make_context(translated_md="   \n  \t  ")
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["non_empty"] is False
        assert any("empty" in f.lower() for f in result["failures"])

    def test_frontmatter_only_passes_nonempty(self) -> None:
        """Frontmatter-only without body is still non-empty."""
        md = "---\nsource_lang: en\ntarget_lang: zh\n---\n"
        ctx = _make_context(translated_md=md)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["non_empty"] is True


# =========================================================================
# GateResult dataclass
# =========================================================================


class TestGateResultDataclass:
    """GateResult dataclass construction."""

    def test_defaults(self) -> None:
        r = GateResult(passed=True)
        assert r.passed is True
        assert r.warnings == []
        assert r.failures == []
        assert r.check_results == {}

    def test_custom_values(self) -> None:
        r = GateResult(
            passed=False,
            warnings=["warn1"],
            failures=["fail1"],
            check_results={"check1": False},
        )
        assert r.passed is False
        assert r.warnings == ["warn1"]
        assert r.failures == ["fail1"]
        assert r.check_results == {"check1": False}


# =========================================================================
# Run vs Execute consistency
# =========================================================================


class TestRunExecuteConsistency:
    """run() and execute() return consistent information."""

    def test_passing_context(self) -> None:
        gate = L4TranslationQuality()
        ctx = _make_context()
        gate_result = gate.run(ctx)
        exec_result = gate.execute(ctx)

        assert gate_result.passed == exec_result["passed"]
        assert gate_result.warnings == exec_result["warnings"]
        assert gate_result.failures == exec_result["failures"]
        assert gate_result.check_results == exec_result["check_results"]

    def test_failing_context(self) -> None:
        gate = L4TranslationQuality()
        ctx = _make_context(translated_md="")
        gate_result = gate.run(ctx)
        exec_result = gate.execute(ctx)

        assert gate_result.passed == exec_result["passed"]
        assert gate_result.warnings == exec_result["warnings"]
        assert gate_result.failures == exec_result["failures"]
        assert gate_result.check_results == exec_result["check_results"]


# =========================================================================
# Edge cases
# =========================================================================


class TestEdgeCases:
    """Edge-case handling."""

    def test_empty_context_does_not_crash(self) -> None:
        result = L4TranslationQuality().execute({})
        assert isinstance(result, dict)
        assert "passed" in result
        assert "warnings" in result
        assert "failures" in result
        assert "check_results" in result

    def test_missing_translation_result(self) -> None:
        result = L4TranslationQuality().execute(
            {"source_lang": "en", "target_lang": "zh"}
        )
        assert result["passed"] is False
        assert result["check_results"]["non_empty"] is False

    def test_garbled_in_frontmatter_only(self) -> None:
        """Garbled chars in the frontmatter section are still detected."""
        md = "---\nsource_lang: en\ntarget_lang: zh\n---\n\ufffdclean body"
        ctx = _make_context(translated_md=md)
        result = L4TranslationQuality().execute(ctx)
        assert result["check_results"]["no_garbled_text"] is False
        assert len(result["warnings"]) > 0

    def test_all_checks_are_reported(self) -> None:
        ctx = _make_context()
        result = L4TranslationQuality().execute(ctx)
        assert set(result["check_results"]) == set(_CHECK_NAMES)

    def test_non_blocking_warnings(self) -> None:
        """Gate can pass with warnings (garbled text is non-blocking)."""
        text = VALID_FRONTMATTER + "Some garbled \ufffd text"
        ctx = _make_context(translated_md=text)
        result = L4TranslationQuality().execute(ctx)
        assert len(result["warnings"]) > 0
        # Frontmatter, language match, and non-empty all pass →
        # no failures, therefore passed=True
        assert result["passed"] is True

    def test_translation_result_as_object(self) -> None:
        """TranslationResult can be an object-style input (not just dict)."""

        class _FakeResult:
            translated_md: str = VALID_FRONTMATTER

        ctx: dict[str, Any] = {
            "translation_result": _FakeResult(),
            "source_lang": "en",
            "target_lang": "zh",
        }
        result = L4TranslationQuality().execute(ctx)
        assert result["passed"] is True
        assert result["check_results"]["frontmatter_valid"] is True

    def test_translation_result_object_missing_field(self) -> None:
        """Object without translated_md defaults to empty string."""

        class _EmptyResult:
            pass

        ctx: dict[str, Any] = {
            "translation_result": _EmptyResult(),
            "source_lang": "en",
            "target_lang": "zh",
        }
        result = L4TranslationQuality().execute(ctx)
        assert result["passed"] is False
        assert result["check_results"]["non_empty"] is False
