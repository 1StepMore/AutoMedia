"""Reusable synthetic gate-context builders for gate/pipeline tests.

Every builder returns a plain ``dict[str, Any]`` suitable for passing
directly to ``Gate.execute(ctx)``.  All data is synthetic — zero
production project data.

Usage::

    from tests.fixtures.synth.gate_contexts import (
        build_humanizer_context,
        build_brand_cta_context,
        build_full_pipeline_context,
    )

    ctx = build_brand_cta_context()
    result = G3BrandCTA().execute(ctx)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent
_BRAND_PROFILES_DIR = _FIXTURES_DIR / "brand_profiles"

_PASS = {"passed": True, "detail": "mock-pass"}

# Every check name across all gates — used to build _mock_results dicts.
_ALL_CHECK_NAMES: list[str] = [
    # pre-gate (topic_selection)
    "topic_not_charity",
    "topic_not_gov_tool",
    "topic_not_investment",
    "topic_not_finance",
    "topic_not_entertainment",
    "topic_length_valid",
    # G0 — fact_check
    "source_trace",
    "number_verification",
    "timeline",
    "quotes",
    "entities",
    # G1 — humanizer
    "overused_adverbs",
    "hollow_intros",
    "vague_subjects",
    "filler_connectors",
    "long_conjunctions",
    "template_conclusions",
    "overacademic_vocabulary",
    "absolute_assertions",
    "repetitive_structures",
    # G2 — copy_review
    "clarity",
    "tone",
    "so_what",
    "evidence",
    "specificity",
    # G3 — brand_cta
    "brand_name_present",
    "cta_present",
    "brand_identity",
    "blocked_words_absent",
    "cta_direction_sync",
    "bridge_sentence",
    # G4 — wechat_checklist
    "title_length",
    "digest_length",
    "no_markdown",
    "cover_exists",
    "tag_count",
    "body_image_count",
    "sensitive_words",
    # G5 — html_hard
    "tag_integrity",
    "no_markdown",
    "tag_count",
    # V0 — lint
    "lint_errors",
    "lint_warnings",
    "syntax_valid",
    # V1 — vision_qa
    "mid_frame_valid",
    "end_silence_valid",
    "all_entries_passed",
    "red_line_6",
    # V2 — pre_send_whisper
    "whisper_transcription",
    "transcription_length",
    "md5_integrity",
    "red_line_7",
    # V3 — content_semantic
    "keyword_coverage",
    "source_alignment",
    "no_hallucination",
    # V4 — tts_brand_asset
    "voice_id_match",
    "speaking_rate",
    "voice_consistency",
    # V5 — mp3_vs_srt
    "whisper_vs_srt_diff",
    "srt_not_empty",
    "whisper_not_empty",
    # V6 — subtitle_render
    "subtitle_region_brightness",
    "subtitle_region_contrast",
    "subtitle_visible",
    "red_line_5",
    # V7 — six_step_hard
    "file_exists",
    "file_size_valid",
    "md5_verified",
    "whisper_full",
    "format_valid",
    "duration_valid",
    # L1 — publish_log_schema
    "topic_present",
    "content_present",
    "media_paths_valid",
    "platform_valid",
    "version_valid",
    "timestamp_valid",
    # L2 — archive_validation
    "archive_status",
    "force_flag",
    "archive_path_exists",
    "archive_metadata_complete",
    "archive_version_valid",
    "output_directory_exists",
    # L3 — platform_integrity
    "all_platforms_present",
    "no_platform_splitting",
    "material_integrity",
    "cross_platform_consistency",
    "format_completeness",
    "metadata_integrity",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_brand_profile(name: str = "testbrand") -> dict[str, Any]:
    """Load a brand profile YAML from ``brand_profiles/`` by name (no extension)."""
    path = _BRAND_PROFILES_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)  # type: ignore[return-value]


def build_all_pass_mock(
    check_names: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return a ``_mock_results`` dict where every check passes."""
    names = check_names or _ALL_CHECK_NAMES
    return {name: dict(_PASS) for name in names}


def build_single_fail_mock(
    fail_name: str,
    detail: str = "mock-fail",
    check_names: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ``_mock_results`` where *fail_name* fails and the rest pass."""
    names = check_names or _ALL_CHECK_NAMES
    results = {name: dict(_PASS) for name in names}
    results[fail_name] = {"passed": False, "detail": detail}
    return results


# ---------------------------------------------------------------------------
# Gate-specific context builders
# ---------------------------------------------------------------------------


def build_topic_selection_context(
    topic: str = "AI technology trends in 2025",
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for the pre-gate topic_selection gate."""
    return {
        "topic": topic,
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "topic_not_charity",
                "topic_not_gov_tool",
                "topic_not_investment",
                "topic_not_finance",
                "topic_not_entertainment",
                "topic_length_valid",
            ]
        ),
    }


def build_fact_check_context(
    topic: str = "AI technology trends in 2025",
    content: str = "AI is transforming industries worldwide.",
    source_data: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for G0 fact_check gate."""
    if source_data is None:
        source_data = {
            "url": "https://example.com/ai-trends-2025",
            "published_date": "2025-06-01T00:00:00+00:00",
            "key_numbers": {"market_size": "$150 billion", "growth_rate": "35%"},
            "entities": ["OpenAI", "Google", "Microsoft"],
            "quotes": ["AI will transform every industry"],
            "reference_text": "example.com",
        }
    return {
        "topic": topic,
        "content": content,
        "source_data": source_data,
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "source_trace",
                "number_verification",
                "timeline",
                "quotes",
                "entities",
            ]
        ),
    }


def build_humanizer_context(
    content: str = (
        "The team finished the project ahead of schedule. "
        "Each member contributed unique skills to the effort. "
        "Results exceeded expectations across all metrics."
    ),
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for G1 humanizer gate."""
    return {
        "content": content,
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "overused_adverbs",
                "hollow_intros",
                "vague_subjects",
                "filler_connectors",
                "long_conjunctions",
                "template_conclusions",
                "overacademic_vocabulary",
                "absolute_assertions",
                "repetitive_structures",
            ]
        ),
    }


def build_copy_review_context(
    content: str = (
        "TestBrand delivers AI内容生产 solutions. Our platform helps teams create content faster."
    ),
    brand_profile: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for G2 copy_review gate."""
    return {
        "content": content,
        "brand_profile": brand_profile or load_brand_profile(),
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "clarity",
                "tone",
                "so_what",
                "evidence",
                "specificity",
            ]
        ),
    }


def build_brand_cta_context(
    content: str = (
        "TestBrand是AI内容生产领域的先行者，专注于用AI驱动内容创作。"
        "如果您想了解我们的服务，立即咨询获取免费试用。"
    ),
    brand_profile: dict[str, Any] | None = None,
    video_script: str | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for G3 brand_cta gate."""
    ctx: dict[str, Any] = {
        "content": content,
        "brand_profile": brand_profile or load_brand_profile(),
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "brand_name_present",
                "cta_present",
                "brand_identity",
                "blocked_words_absent",
                "cta_direction_sync",
                "bridge_sentence",
            ]
        ),
    }
    if video_script is not None:
        ctx["video_script"] = video_script
    return ctx


def build_wechat_checklist_context(
    content: str = "<p>TestBrand delivers AI内容生产 solutions.</p>",
    title: str = "AI趋势",
    digest: str = "AI trends 2025 overview",
    cover_image: str = "https://example.com/cover.jpg",
    tags: list[str] | None = None,
    body_images: list[str] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for G4 wechat_checklist gate."""
    return {
        "content": content,
        "title": title,
        "digest": digest,
        "cover_image": cover_image,
        "tags": tags or ["AI", "tech", "trends", "2025", "innovation"],
        "body_images": body_images
        or [
            "<img src='a.jpg'>",
            "<img src='b.jpg'>",
            "<img src='c.jpg'>",
            "<img src='d.jpg'>",
        ],
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "title_length",
                "digest_length",
                "no_markdown",
                "cover_exists",
                "tag_count",
                "body_image_count",
                "sensitive_words",
            ]
        ),
    }


def build_lint_context(
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for V0 lint gate."""
    return {
        "lint_result": {"errors": 0, "warnings": 0, "syntax_ok": True},
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "lint_errors",
                "lint_warnings",
                "syntax_valid",
            ]
        ),
    }


def build_vision_qa_context(
    entries: list[dict[str, Any]] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
    base_dir: str = "/tmp",
) -> dict[str, Any]:
    """Build context for V1 vision_qa gate."""
    if entries is None:
        entries = [
            {
                "mid_frame_path": f"{base_dir}/frame_{i}.png",
                "end_silence_frame_path": f"{base_dir}/end_{i}.png",
                "qa_passed": True,
                "checked": True,
            }
            for i in range(5)
        ]
    return {
        "entries": entries,
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "mid_frame_valid",
                "end_silence_valid",
                "all_entries_passed",
                "red_line_6",
            ]
        ),
    }


def build_whisper_context(
    mock_results: dict[str, dict[str, Any]] | None = None,
    base_dir: str = "/tmp",
) -> dict[str, Any]:
    """Build context for V2 pre_send_whisper gate."""
    return {
        "transcription": "Full audio transcription text for testing purposes.",
        "audio_path": f"{base_dir}/test_audio.mp3",
        "expected_md5": "",
        "full_audio": True,
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "whisper_transcription",
                "transcription_length",
                "md5_integrity",
                "red_line_7",
            ]
        ),
    }


def build_content_semantic_context(
    source_keywords: list[str] | None = None,
    content_keywords: list[str] | None = None,
    source_texts: list[str] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for V3 content_semantic gate."""
    return {
        "source_keywords": source_keywords or ["AI", "technology", "trends", "2025", "production"],
        "content_keywords": content_keywords
        or ["AI", "technology", "trends", "2025", "production"],
        "source_texts": source_texts
        or [
            "Source 1 about AI trends in 2025.",
            "Source 2 about content production.",
            "Source 3 about technology advances.",
        ],
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "keyword_coverage",
                "source_alignment",
                "no_hallucination",
            ]
        ),
    }


def build_tts_brand_context(
    voice_id: str = "brand_voice_001",
    expected_voice_id: str = "brand_voice_001",
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for V4 tts_brand_asset gate."""
    return {
        "voice_id": voice_id,
        "expected_voice_id": expected_voice_id,
        "speaking_rate": 1.0,
        "segments": [
            {"voice_params": {"pitch": 0, "rate": 1.0}},
            {"voice_params": {"pitch": 0, "rate": 1.0}},
        ],
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "voice_id_match",
                "speaking_rate",
                "voice_consistency",
            ]
        ),
    }


def build_mp3_vs_srt_context(
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for V5 mp3_vs_srt gate."""
    return {
        "whisper_text": "Hello world, this is a test transcription.",
        "srt_text": (
            "1\n00:00:00,000 --> 00:00:02,000\nHello world, this is a test transcription.\n"
        ),
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "whisper_vs_srt_diff",
                "srt_not_empty",
                "whisper_not_empty",
            ]
        ),
    }


def build_subtitle_render_context(
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for V6 subtitle_render gate."""
    return {
        "avg_brightness": 128,
        "contrast": 150,
        "opacity": 1.0,
        "pixel_valid": True,
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "subtitle_region_brightness",
                "subtitle_region_contrast",
                "subtitle_visible",
                "red_line_5",
            ]
        ),
    }


def build_six_step_hard_context(
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for V7 six_step_hard gate."""
    return {
        "required_files": [],
        "file_sizes": {},
        "md5_records": {},
        "whisper_full_audio": True,
        "actual_format": "mp4",
        "expected_format": "mp4",
        "actual_duration": 120.0,
        "expected_duration_min": 60.0,
        "expected_duration_max": 180.0,
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "file_exists",
                "file_size_valid",
                "md5_verified",
                "whisper_full",
                "format_valid",
                "duration_valid",
            ]
        ),
    }


def build_publish_log_context(
    topic: str = "AI technology trends in 2025",
    mock_results: dict[str, dict[str, Any]] | None = None,
    base_dir: str = "/tmp",
) -> dict[str, Any]:
    """Build context for L1 publish_log_schema gate."""
    return {
        "publish_log": {
            "topic": topic,
            "content": "Test article content for publish log.",
            "media_paths": [f"{base_dir}/output/video.mp4"],
            "platform": "wechat",
            "version": "1.0",
            "created_at": "2025-06-01T12:00:00",
        },
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "topic_present",
                "content_present",
                "media_paths_valid",
                "platform_valid",
                "version_valid",
                "timestamp_valid",
            ]
        ),
    }


def build_archive_validation_context(
    mock_results: dict[str, dict[str, Any]] | None = None,
    base_dir: str = "/tmp",
) -> dict[str, Any]:
    """Build context for L2 archive_validation gate."""
    return {
        "archive_status": "published",
        "force": True,
        "archive_path": f"{base_dir}/archive.zip",
        "archive_metadata": {
            "title": "AI Trends 2025",
            "platform": "wechat",
            "created_at": "2025-06-01T12:00:00",
        },
        "output_dir": f"{base_dir}/output",
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "archive_status",
                "force_flag",
                "archive_path_exists",
                "archive_metadata_complete",
                "archive_version_valid",
                "output_directory_exists",
            ]
        ),
    }


def build_platform_integrity_context(
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for L3 platform_integrity gate."""
    return {
        "platforms": ["wechat", "weibo"],
        "expected_platforms": ["wechat", "weibo"],
        "unified_content": "Unified content body for all platforms.",
        "media_files": [],
        "file_paths": [],
        "formats": ["mp4", "txt", "json"],
        "required_formats": ["mp4", "txt", "json"],
        "_mock_results": mock_results
        or build_all_pass_mock(
            [
                "all_platforms_present",
                "no_platform_splitting",
                "material_integrity",
                "cross_platform_consistency",
                "format_completeness",
                "metadata_integrity",
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Full pipeline context builder
# ---------------------------------------------------------------------------


def build_full_pipeline_context(
    topic: str = "AI technology trends in 2025",
    brand_profile: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
    project_dir: str = "/projects/test_project",
) -> dict[str, Any]:
    """Build a mega-context that satisfies every gate's expected keys.

    Combines data from all gate-specific builders into a single dict
    suitable for ``GateEngine.run(ctx)``.
    """
    if brand_profile is None:
        brand_profile = load_brand_profile()
    if mock_results is None:
        mock_results = build_all_pass_mock()

    content = (
        "TestBrand是AI内容生产领域的先行者，专注于用AI驱动内容创作。"
        "如果您想了解我们的服务，立即咨询获取免费试用。"
    )

    return {
        # Shared
        "topic": topic,
        "project_dir": project_dir,
        "force_provenance": True,
        "content": content,
        "brand_profile": brand_profile,
        "source_data": {
            "url": "https://example.com/ai-trends-2025",
            "published_date": "2025-06-01T00:00:00+00:00",
            "key_numbers": {"market_size": "$150 billion"},
            "entities": ["OpenAI"],
            "quotes": ["AI will transform every industry"],
        },
        "_mock_results": mock_results,
        # G4
        "title": "AI趋势",
        "digest": "AI trends overview",
        "cover_image": "https://example.com/cover.jpg",
        "tags": ["AI", "tech", "trends", "2025", "innovation"],
        "body_images": [
            "<img src='a.jpg'>",
            "<img src='b.jpg'>",
            "<img src='c.jpg'>",
            "<img src='d.jpg'>",
        ],
        # V0
        "lint_result": {"errors": 0, "warnings": 0, "syntax_ok": True},
        # V1
        "entries": [
            {
                "mid_frame_path": f"{project_dir}/frame_{i}.png",
                "end_silence_frame_path": f"{project_dir}/end_{i}.png",
                "qa_passed": True,
                "checked": True,
            }
            for i in range(5)
        ],
        # V2
        "transcription": "Full audio transcription text for testing.",
        "audio_path": f"{project_dir}/test.mp3",
        "expected_md5": "",
        "full_audio": True,
        # V3
        "source_keywords": ["AI", "technology", "trends"],
        "content_keywords": ["AI", "technology", "trends"],
        "source_texts": ["Source 1.", "Source 2.", "Source 3."],
        # V4
        "voice_id": "brand_voice_001",
        "expected_voice_id": "brand_voice_001",
        "speaking_rate": 1.0,
        "segments": [
            {"voice_params": {"pitch": 0, "rate": 1.0}},
            {"voice_params": {"pitch": 0, "rate": 1.0}},
        ],
        # V5
        "whisper_text": "Hello world, this is a test transcription.",
        "srt_text": (
            "1\n00:00:00,000 --> 00:00:02,000\nHello world, this is a test transcription.\n"
        ),
        # V6
        "avg_brightness": 128,
        "contrast": 150,
        "opacity": 1.0,
        "pixel_valid": True,
        # V7
        "required_files": [],
        "file_sizes": {},
        "md5_records": {},
        "whisper_full_audio": True,
        "actual_format": "mp4",
        "expected_format": "mp4",
        "actual_duration": 120.0,
        "expected_duration_min": 60.0,
        "expected_duration_max": 180.0,
        # L1
        "publish_log": {
            "topic": topic,
            "content": "Test article content.",
            "media_paths": [f"{project_dir}/video.mp4"],
            "platform": "wechat",
            "version": "1.0",
            "created_at": "2025-06-01T12:00:00",
        },
        # L2
        "archive_status": "published",
        "force": True,
        "archive_path": f"{project_dir}/archive.zip",
        "archive_metadata": {
            "title": "AI Trends 2025",
            "platform": "wechat",
            "created_at": "2025-06-01T12:00:00",
        },
        "archive_version": "1.0",
        "output_dir": f"{project_dir}/output",
        # L3
        "platforms": ["wechat", "weibo"],
        "expected_platforms": ["wechat", "weibo"],
        "unified_content": "Unified content body for all platforms.",
        "media_files": [],
        "file_paths": [],
        "formats": ["mp4", "txt", "json"],
        "required_formats": ["mp4", "txt", "json"],
        # L4
        "translation_result": {
            "translated_md": "---\nsource_lang: zh\ntarget_lang: en\n---\nTranslated content here."
        },
        "source_lang": "zh",
        "target_lang": "en",
    }
