"""E2E: Multilingual pipeline — language configuration injection and resolution.

Verifies that ``run_full_pipeline`` correctly injects ``lang_config`` into
``gate_context`` when ``default_lang`` is specified, and that the
``resolve_language_config`` function returns appropriate TTS, Whisper, CTA,
blocked-words and date-format values for both English and Chinese.

PRD-1 M4: "全链路打通 multilingual — default_lang='en' 注入后, gate_context
中的 lang_config 正确切换为英文 TTS/Whisper/CTA"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.manifests.brand_profile_schema import BrandProfile
from automedia.pipelines.gate_engine import GateEngine
from automedia.pipelines.language_config import resolve_language_config
from automedia.pipelines.runner import run_full_pipeline


# ---------------------------------------------------------------------------
# Expected values — specific strings required by the spec
# ---------------------------------------------------------------------------

EN_TTS_VOICE: str = "en-US-JennyNeural"
EN_WHISPER_LANG: str = "en"
EN_CTA_TEMPLATE: str = "Try {brand} today"
EN_BLOCKED_WORDS: list[str] = ["competitor_a", "competitor_b"]
EN_DATE_FORMAT: str = "MM/DD/YYYY"

ZH_TTS_VOICE: str = "zh-CN-YunxiNeural"
ZH_WHISPER_LANG: str = "zh"
# zh-CN defaults from _ZH_DEFAULTS in language_config.py
ZH_CTA_TEMPLATE: str = ""
ZH_BLOCKED_WORDS: list[str] = []
ZH_DATE_FORMAT: str = ""


# ---------------------------------------------------------------------------
# Helpers — brand-profile builders
# ---------------------------------------------------------------------------


def _build_bilingual_profile(brand_name: str = "TestBrand") -> BrandProfile:
    """Build a BrandProfile with both ``en`` and ``zh`` language configs.

    The English config contains real-looking TTS, Whisper, CTA, blocked-words
    and date-format values.  The Chinese config mirrors ``_ZH_DEFAULTS``.
    """
    return BrandProfile(
        brand_name=brand_name,
        languages={
            "en": {
                "tts_voice": EN_TTS_VOICE,
                "whisper_lang": EN_WHISPER_LANG,
                "cta_template": EN_CTA_TEMPLATE,
                "blocked_words": EN_BLOCKED_WORDS,
                "date_format": EN_DATE_FORMAT,
            },
            "zh": {
                "tts_voice": ZH_TTS_VOICE,
                "whisper_lang": ZH_WHISPER_LANG,
            },
        },
    )


def _build_zh_only_profile(brand_name: str = "TestBrand") -> BrandProfile:
    """Build a BrandProfile with only ``zh`` language config (no ``en``)."""
    return BrandProfile(
        brand_name=brand_name,
        languages={
            "zh": {
                "tts_voice": ZH_TTS_VOICE,
                "whisper_lang": ZH_WHISPER_LANG,
            },
        },
    )


def _mock_project(tmp_path: Path, project_id: str = "test-proj") -> MagicMock:
    """Build a mock Project with the given temp directory as project_dir."""
    proj = MagicMock()
    proj.project_id = project_id
    proj.project_dir = str(tmp_path)
    return proj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestMultilingualEnglishPipeline:
    """End-to-end tests for the English full-chain pipeline with language selection.

    Every test that touches ``run_full_pipeline`` patches the runner's external
    dependencies (``load_config``, ``Project``, ``load_brand_profile``,
    ``GateEngine``) so that **no real filesystem or network operations** are
    performed.
    """

    # ------------------------------------------------------------------
    # Integration: run_full_pipeline with default_lang="en"
    # ------------------------------------------------------------------

    @patch("automedia.pipelines.runner.load_config")
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner.load_brand_profile")
    @patch("automedia.pipelines.runner.GateEngine")
    def test_run_full_pipeline_injects_lang_config_with_en(
        self,
        mock_ge_cls: MagicMock,
        mock_load_bp: MagicMock,
        mock_project_cls: MagicMock,
        mock_load_config: MagicMock,
        sample_topic: str,
        tmp_path: Path,
    ) -> None:
        """``run_full_pipeline(topic, brand, default_lang="en")`` injects
        ``lang_config`` with English TTS/Whisper/CTA/blocked-words/date-format
        into ``gate_context``."""
        # --- Arrange ---
        mock_load_config.return_value = {"content": {"default_language": "zh"}}

        mock_project = _mock_project(tmp_path, "test-proj-01")
        mock_project_cls.init.return_value = mock_project

        mock_load_bp.return_value = _build_bilingual_profile()

        captured_context: dict[str, Any] = {}

        def _capturing_run(ctx: dict[str, Any], **kwargs: Any) -> tuple[bool, list[dict]]:
            captured_context.update(ctx)
            return True, [{"passed": True, "gate": "CW", "duration_s": 0.1}]

        mock_engine = MagicMock()
        mock_engine.run.side_effect = _capturing_run
        mock_ge_cls.return_value = mock_engine

        # --- Act ---
        result = run_full_pipeline(
            sample_topic,
            "TestBrand",
            default_lang="en",
        )

        # --- Assert ---
        assert result.status == "success", (
            f"Pipeline should succeed when GateEngine.run is mocked. "
            f"Got status={result.status!r}, error={result.error}"
        )
        assert "lang_config" in captured_context, (
            "gate_context must contain 'lang_config' key when "
            "default_lang is provided"
        )

        lang_config = captured_context["lang_config"]
        assert lang_config["tts_voice"] == EN_TTS_VOICE, (
            f"Expected tts_voice={EN_TTS_VOICE!r}, "
            f"got {lang_config['tts_voice']!r}"
        )
        assert lang_config["whisper_lang"] == EN_WHISPER_LANG, (
            f"Expected whisper_lang={EN_WHISPER_LANG!r}, "
            f"got {lang_config['whisper_lang']!r}"
        )
        assert lang_config["cta_template"] == EN_CTA_TEMPLATE, (
            f"Expected cta_template={EN_CTA_TEMPLATE!r}, "
            f"got {lang_config['cta_template']!r}"
        )
        assert lang_config["blocked_words"] == EN_BLOCKED_WORDS, (
            f"Expected blocked_words={EN_BLOCKED_WORDS!r}, "
            f"got {lang_config['blocked_words']!r}"
        )
        assert lang_config["date_format"] == EN_DATE_FORMAT, (
            f"Expected date_format={EN_DATE_FORMAT!r}, "
            f"got {lang_config['date_format']!r}"
        )

        # --- Verify additional gate_context keys are present ---
        assert "topic" in captured_context
        assert "brand" in captured_context
        assert "project_id" in captured_context
        assert "project_dir" in captured_context
        assert "config" in captured_context
        assert "tenant_id" in captured_context

    # ------------------------------------------------------------------
    # Integration: run_full_pipeline without default_lang → zh-CN
    # ------------------------------------------------------------------

    @patch("automedia.pipelines.runner.load_config")
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner.load_brand_profile")
    @patch("automedia.pipelines.runner.GateEngine")
    def test_run_full_pipeline_defaults_to_zh_cn(
        self,
        mock_ge_cls: MagicMock,
        mock_load_bp: MagicMock,
        mock_project_cls: MagicMock,
        mock_load_config: MagicMock,
        sample_topic: str,
        tmp_path: Path,
    ) -> None:
        """``run_full_pipeline(...)`` without ``default_lang`` produces
        ``lang_config`` with zh-CN default values (``zh-CN-YunxiNeural``,
        ``zh``, empty CTA/blocked-words/date-format).

        This validates the fallback chain: no brand profile found →
        ``resolve_language_config`` returns hard-coded ``_ZH_DEFAULTS``.
        """
        # --- Arrange ---
        mock_load_config.return_value = {"content": {"default_language": "zh"}}

        mock_project = _mock_project(tmp_path, "test-proj-02")
        mock_project_cls.init.return_value = mock_project

        # No brand-profile.yaml exists → load_brand_profile raises
        mock_load_bp.side_effect = FileNotFoundError(
            "brand-profile.yaml not found"
        )

        captured_context: dict[str, Any] = {}

        def _capturing_run(ctx: dict[str, Any], **kwargs: Any) -> tuple[bool, list[dict]]:
            captured_context.update(ctx)
            return True, [{"passed": True, "gate": "CW", "duration_s": 0.1}]

        mock_engine = MagicMock()
        mock_engine.run.side_effect = _capturing_run
        mock_ge_cls.return_value = mock_engine

        # --- Act ---
        # Intentionally omit default_lang
        result = run_full_pipeline(sample_topic, "TestBrand")

        # --- Assert ---
        assert result.status == "success", (
            f"Pipeline should succeed. Got status={result.status!r}"
        )
        assert "lang_config" in captured_context

        lang_config = captured_context["lang_config"]
        assert lang_config["tts_voice"] == ZH_TTS_VOICE, (
            f"Expected zh-CN tts_voice={ZH_TTS_VOICE!r}, "
            f"got {lang_config['tts_voice']!r}"
        )
        assert lang_config["whisper_lang"] == ZH_WHISPER_LANG, (
            f"Expected zh-CN whisper_lang={ZH_WHISPER_LANG!r}, "
            f"got {lang_config['whisper_lang']!r}"
        )
        assert lang_config["cta_template"] == ZH_CTA_TEMPLATE, (
            f"Expected empty zh-CN cta_template, "
            f"got {lang_config['cta_template']!r}"
        )
        assert lang_config["blocked_words"] == ZH_BLOCKED_WORDS, (
            f"Expected empty zh-CN blocked_words, "
            f"got {lang_config['blocked_words']!r}"
        )
        assert lang_config["date_format"] == ZH_DATE_FORMAT, (
            f"Expected empty zh-CN date_format, "
            f"got {lang_config['date_format']!r}"
        )

    # ------------------------------------------------------------------
    # Unit: resolve_language_config — English
    # ------------------------------------------------------------------

    def test_resolve_language_config_returns_english_values(self) -> None:
        """``resolve_language_config(profile_with_en, "en")`` returns English
        TTS (``en-US-JennyNeural``), Whisper (``en``), CTA template, blocked
        words and date format."""
        profile = _build_bilingual_profile()

        lang_config = resolve_language_config(profile, "en")

        assert lang_config["tts_voice"] == EN_TTS_VOICE
        assert lang_config["whisper_lang"] == EN_WHISPER_LANG
        assert lang_config["cta_template"] == EN_CTA_TEMPLATE
        assert lang_config["blocked_words"] == EN_BLOCKED_WORDS
        assert lang_config["date_format"] == EN_DATE_FORMAT

    # ------------------------------------------------------------------
    # Unit: resolve_language_config — fallback
    # ------------------------------------------------------------------

    def test_resolve_language_config_fallback_when_lang_unavailable(self) -> None:
        """``resolve_language_config(zh_only_profile, "en")`` falls back to
        zh-CN values when ``"en"`` is not present in the brand profile's
        ``languages`` dict."""
        profile = _build_zh_only_profile()

        lang_config = resolve_language_config(profile, "en")

        # Falls back to zh values because "en" is missing from the profile
        assert lang_config["tts_voice"] == ZH_TTS_VOICE, (
            f"Expected zh-CN fallback tts_voice={ZH_TTS_VOICE!r}, "
            f"got {lang_config['tts_voice']!r}"
        )
        assert lang_config["whisper_lang"] == ZH_WHISPER_LANG, (
            f"Expected zh-CN fallback whisper_lang={ZH_WHISPER_LANG!r}, "
            f"got {lang_config['whisper_lang']!r}"
        )

    def test_resolve_language_config_fallback_no_profile(self) -> None:
        """``resolve_language_config(None, "en")`` returns hard-coded zh-CN
        defaults when no brand profile is available."""
        lang_config = resolve_language_config(None, "en")

        assert lang_config["tts_voice"] == ZH_TTS_VOICE
        assert lang_config["whisper_lang"] == ZH_WHISPER_LANG
        assert lang_config["cta_template"] == ZH_CTA_TEMPLATE
        assert lang_config["blocked_words"] == ZH_BLOCKED_WORDS
        assert lang_config["date_format"] == ZH_DATE_FORMAT

    def test_resolve_language_config_default_lang_none_equals_zh(self) -> None:
        """``resolve_language_config(None, None)`` treats ``None`` as ``"zh"``
        and returns zh-CN defaults."""
        lang_config = resolve_language_config(None, None)

        assert lang_config["tts_voice"] == ZH_TTS_VOICE
        assert lang_config["whisper_lang"] == ZH_WHISPER_LANG

    # ------------------------------------------------------------------
    # Mock GateEngine capture: verify lang_config reaches the engine
    # ------------------------------------------------------------------

    @patch("automedia.pipelines.runner.load_config")
    @patch("automedia.pipelines.runner.Project")
    @patch("automedia.pipelines.runner.load_brand_profile")
    def test_gate_context_includes_lang_config_via_mock_engine(
        self,
        mock_load_bp: MagicMock,
        mock_project_cls: MagicMock,
        mock_load_config: MagicMock,
        sample_topic: str,
        tmp_path: Path,
    ) -> None:
        """``GateEngine.run`` receives ``gate_context`` with ``lang_config``
        injected when ``default_lang="en"``.

        This test patches ``GateEngine.run`` **directly on the class** so
        that the real ``GateEngine.__init__`` (and gate construction) still
        executes — only the ``run`` method is intercepted to capture the
        context that the runner passes to it.
        """
        # --- Arrange ---
        mock_load_config.return_value = {"content": {"default_language": "zh"}}

        mock_project = _mock_project(tmp_path, "test-proj-05")
        mock_project_cls.init.return_value = mock_project

        mock_load_bp.return_value = _build_bilingual_profile()

        captured_context: dict[str, Any] = {}

        def _capturing_run(
            engine_self: GateEngine,
            gate_context: dict[str, Any],
            **kwargs: Any,
        ) -> tuple[bool, list[dict]]:
            captured_context.update(gate_context)
            return True, [{"passed": True, "gate": "CW", "duration_s": 0.1}]

        with patch.object(GateEngine, "run", _capturing_run):
            # --- Act ---
            result = run_full_pipeline(
                sample_topic,
                "TestBrand",
                default_lang="en",
            )

        # --- Assert ---
        assert result.status == "success", (
            f"Pipeline should succeed. Got status={result.status!r}"
        )
        assert "lang_config" in captured_context, (
            "gate_context must contain 'lang_config' when "
            "default_lang='en'"
        )

        lang_config = captured_context["lang_config"]
        assert lang_config["tts_voice"] == EN_TTS_VOICE, (
            f"Expected tts_voice={EN_TTS_VOICE!r}, "
            f"got {lang_config['tts_voice']!r}"
        )
        assert lang_config["whisper_lang"] == EN_WHISPER_LANG, (
            f"Expected whisper_lang={EN_WHISPER_LANG!r}, "
            f"got {lang_config['whisper_lang']!r}"
        )
        assert lang_config["cta_template"] == EN_CTA_TEMPLATE, (
            f"Expected cta_template={EN_CTA_TEMPLATE!r}, "
            f"got {lang_config['cta_template']!r}"
        )
        assert lang_config["blocked_words"] == EN_BLOCKED_WORDS, (
            f"Expected blocked_words={EN_BLOCKED_WORDS!r}, "
            f"got {lang_config['blocked_words']!r}"
        )
        assert lang_config["date_format"] == EN_DATE_FORMAT, (
            f"Expected date_format={EN_DATE_FORMAT!r}, "
            f"got {lang_config['date_format']!r}"
        )

        # — Verify the full context also contains expected non-lang keys —
        assert captured_context.get("topic") == sample_topic
        assert captured_context.get("brand") == "TestBrand"
        assert captured_context.get("project_id") == "test-proj-05"
        assert captured_context.get("project_dir") == str(tmp_path)
        assert captured_context.get("tenant_id") == "default"
