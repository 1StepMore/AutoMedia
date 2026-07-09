"""Language selection — resolve locale-specific configuration for the pipeline.

Public API
----------
- ``resolve_language_config(brand_profile, default_lang="zh")`` — return a
  dict with ``tts_voice``, ``whisper_lang``, ``cta_template``,
  ``blocked_words``, and ``date_format`` for the given brand profile and
  requested language.
"""

from __future__ import annotations

from typing import Any

from automedia.manifests.brand_profile_schema import BrandProfile

# ---------------------------------------------------------------------------
# Hard-coded fallback defaults (zh-CN)
# ---------------------------------------------------------------------------

_ZH_DEFAULTS: dict[str, Any] = {
    "tts_voice": "zh-CN-YunxiNeural",
    "whisper_lang": "zh",
    "cta_template": "",
    "blocked_words": [],
    "date_format": "",
}

_LANG_FIELDS: tuple[str, ...] = (
    "tts_voice",
    "whisper_lang",
    "cta_template",
    "blocked_words",
    "date_format",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_language_config(
    brand_profile: BrandProfile | None,
    default_lang: str | None = "zh",
) -> dict[str, Any]:
    """Resolve locale-specific configuration for the pipeline.

    The function follows a fallback chain:

    1. If ``brand_profile`` is not ``None`` and ``languages`` contains
       *default_lang*, return the values configured for that language.
    2. Otherwise if ``brand_profile`` contains ``"zh"``, return zh-CN values.
    3. Otherwise return the hard-coded zh-CN defaults (``_ZH_DEFAULTS``).

    Parameters
    ----------
    brand_profile:
        Optional :class:`BrandProfile` dataclass with a ``languages``
        dictionary.  ``None`` is handled gracefully.
    default_lang:
        Requested language code (e.g. ``"zh"``, ``"en"``).  ``None`` is
        treated as ``"zh"``.

    Returns
    -------
    dict[str, Any]
        Dictionary with keys ``tts_voice``, ``whisper_lang``,
        ``cta_template``, ``blocked_words``, ``date_format``.
    """
    effective_lang = default_lang or "zh"

    # Attempt to read from the brand profile's languages dict
    if brand_profile is not None and brand_profile.languages:
        lang_data = brand_profile.languages.get(effective_lang)
        if lang_data is not None:
            return _extract_lang(lang_data)

        # Fallback: try zh, then hard-coded defaults
        zh_data = brand_profile.languages.get("zh")
        if zh_data is not None:
            return _extract_lang(zh_data)

    return dict(_ZH_DEFAULTS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_lang(data: dict[str, Any]) -> dict[str, Any]:
    """Extract known fields from a language data dict, filling missing ones
    with empty / sensible defaults."""
    result: dict[str, Any] = {}
    for field in _LANG_FIELDS:
        # tts_voice and whisper_lang are non-optional — fall back to zh-CN
        # values; other fields fall back to empty.
        value = data.get(field)
        if value is not None:
            result[field] = value
        elif field in ("tts_voice", "whisper_lang"):
            result[field] = _ZH_DEFAULTS[field]
        else:
            result[field] = _ZH_DEFAULTS.get(field, "")
    return result