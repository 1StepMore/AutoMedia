"""RED tests for ``resolve_language_config()`` — language selection logic.

Scenarios
---------
1. ``default_lang="zh"`` → zh-CN defaults (current behaviour)
2. ``default_lang="en"`` → en-US TTS/Whisper/CTA
3. ``languages.en`` with explicit ``cta_template`` → CTA from config
4. Missing language configuration → graceful fallback to zh-CN defaults
5. ``default_lang=None`` → defaults to "zh"
6. Return dict contains all expected keys
"""

from __future__ import annotations

from automedia.manifests.brand_profile_schema import BrandProfile

# =====================================================================
# Helpers
# =====================================================================

_EN_PROFILE = BrandProfile(
    brand_name="TestBrand",
    languages={
        "en": {
            "tts_voice": "en-US-JennyNeural",
            "whisper_lang": "en",
            "cta_template": "Check out {brand} today!",
            "blocked_words": ["competitor"],
            "date_format": "MM/DD/YYYY",
        },
        "zh": {
            "tts_voice": "zh-CN-YunxiNeural",
            "whisper_lang": "zh",
            "cta_template": "立即体验 {brand}！",
            "blocked_words": ["竞品"],
            "date_format": "YYYY-MM-DD",
        },
    },
)

_ZH_PROFILE = BrandProfile(
    brand_name="TestBrand",
    languages={
        "zh": {
            "tts_voice": "zh-CN-YunxiNeural",
            "whisper_lang": "zh",
            "cta_template": "立即体验 {brand}！",
            "blocked_words": ["竞品"],
            "date_format": "YYYY-MM-DD",
        },
    },
)

_EMPTY_PROFILE = BrandProfile(brand_name="NoLang")
_NONE_PROFILE: BrandProfile | None = None


# ======================================================================
# Tests — these will all fail (RED) until language_config module exists
# ======================================================================


class TestDefaultLangZh:
    """``default_lang="zh"`` returns zh-CN defaults."""

    def test_zh_tts_voice(self) -> None:
        """zh profile + zh → zh-CN-YunxiNeural TTS."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        assert config["tts_voice"] == "zh-CN-YunxiNeural"

    def test_zh_whisper_lang(self) -> None:
        """zh profile + zh → 'zh' whisper lang."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        assert config["whisper_lang"] == "zh"

    def test_zh_cta_template(self) -> None:
        """zh profile + zh → CTA from config."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        assert config["cta_template"] == "立即体验 {brand}！"

    def test_zh_blocked_words(self) -> None:
        """zh profile + zh → blocked_words from config."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        assert "竞品" in config["blocked_words"]

    def test_zh_date_format(self) -> None:
        """zh profile + zh → date_format from config."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        assert config["date_format"] == "YYYY-MM-DD"


class TestDefaultLangEn:
    """``default_lang="en"`` returns en-US English configuration."""

    def test_en_tts_voice(self) -> None:
        """En profile + en → en-US-JennyNeural TTS."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_EN_PROFILE, default_lang="en")
        assert config["tts_voice"] == "en-US-JennyNeural"

    def test_en_whisper_lang(self) -> None:
        """En profile + en → 'en' whisper lang."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_EN_PROFILE, default_lang="en")
        assert config["whisper_lang"] == "en"

    def test_en_cta_template(self) -> None:
        """En profile + en → CTA template from config."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_EN_PROFILE, default_lang="en")
        assert config["cta_template"] == "Check out {brand} today!"

    def test_en_blocked_words(self) -> None:
        """En profile + en → blocked_words from config."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_EN_PROFILE, default_lang="en")
        assert "competitor" in config["blocked_words"]

    def test_en_date_format(self) -> None:
        """En profile + en → date_format from config."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_EN_PROFILE, default_lang="en")
        assert config["date_format"] == "MM/DD/YYYY"


class TestFallbackBehaviour:
    """When requested language is missing → fall back to zh-CN."""

    def test_en_not_configured_falls_to_zh(self) -> None:
        """Only zh configured, default_lang=en → still zh-CN defaults."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="en")
        assert config["tts_voice"] == "zh-CN-YunxiNeural"
        assert config["whisper_lang"] == "zh"

    def test_no_languages_configured(self) -> None:
        """Empty profile → hardcoded zh-CN defaults."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_EMPTY_PROFILE, default_lang="en")
        assert config["tts_voice"] == "zh-CN-YunxiNeural"
        assert config["whisper_lang"] == "zh"
        assert config["cta_template"] == ""
        assert config["blocked_words"] == []
        assert config["date_format"] == ""

    def test_none_profile(self) -> None:
        """None profile → hardcoded zh-CN defaults."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(None, default_lang="en")
        assert config["tts_voice"] == "zh-CN-YunxiNeural"
        assert config["whisper_lang"] == "zh"

    def test_default_lang_none(self) -> None:
        """default_lang=None → defaults to 'zh'."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang=None)
        assert config["tts_voice"] == "zh-CN-YunxiNeural"
        assert config["whisper_lang"] == "zh"


class TestReturnStructure:
    """Return dict structure is correct."""

    def test_all_keys_present(self) -> None:
        """Return dict contains all expected keys."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        expected_keys = {
            "tts_voice",
            "whisper_lang",
            "cta_template",
            "blocked_words",
            "date_format",
        }
        assert set(config.keys()) == expected_keys

    def test_dict_is_immutable_copy(self) -> None:
        """Returned dict should not share reference with profile."""
        from automedia.pipelines.language_config import resolve_language_config

        config = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        config["tts_voice"] = "hacked"
        # original should be unchanged
        config2 = resolve_language_config(_ZH_PROFILE, default_lang="zh")
        assert config2["tts_voice"] == "zh-CN-YunxiNeural"
