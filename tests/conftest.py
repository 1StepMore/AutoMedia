"""Shared pytest fixtures and configuration for AutoMedia E2E tests.

All fixtures produce synthetic data — zero production project data.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# pytest hooks
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers and warning filters."""

    config.addinivalue_line("markers", "e2e: end-to-end pipeline integration tests")
    config.addinivalue_line("markers", "redline: red-line enforcement tests")
    config.addinivalue_line("markers", "slow: tests that take more than a few seconds")
    config.addinivalue_line("markers", "cruel: cruel acceptance tests requiring real API access")
    # Suppress RL7 warnings for test-only gate names (G-prefixed test gates
    # are not in failure_modes.py — this is expected).
    config.addinivalue_line(
        "filterwarnings",
        "ignore:Gate 'G[0-9]+' is registered but missing from FAILURE_MODES",
    )


# ---------------------------------------------------------------------------
# Directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _gate_registry_isolation() -> Generator[None, None, None]:
    """Save and restore :class:`GateRegistry` state between tests.

    ``GateRegistry`` is a singleton — concrete :class:`BaseGate` subclasses
    (including test-only ones like ``_AlwaysPassGate``) register themselves
    via ``__init_subclass__``.  Without isolation the registry state leaks
    across test files, causing false ``KeyError`` duplicates or phantom
    registrations.
    """
    from automedia.gates.base import GateRegistry

    registry = GateRegistry()
    saved = dict(registry._registry)  # noqa: SLF001  # intentional test isolation
    yield
    registry._registry.clear()
    registry._registry.update(saved)


@pytest.fixture()
def tmp_project_dir(tmp_path: Any) -> Any:
    """Create a temporary project directory with basic structure.

    Returns the ``tmp_path`` so tests can build on it.
    """
    (tmp_path / "output").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / ".automedia").mkdir()
    return tmp_path


@pytest.fixture()
def mock_config_dir(tmp_path: Any) -> Any:
    """Create a temporary configuration directory with a minimal config file.

    Returns the directory path.
    """
    config_dir = tmp_path / ".automedia"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.yaml"
    config_file.write_text(
        "brand: TestBrand\ntenant_id: test\nmode: auto\n",
        encoding="utf-8",
    )
    return config_dir


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_topic() -> str:
    """A safe synthetic topic that passes TopicSelectionGate."""
    return "AI technology trends in 2025"


@pytest.fixture()
def sample_brand_profile() -> dict[str, Any]:
    """Synthetic brand profile — no real brand data."""
    return {
        "brand_name": "TestBrand",
        "brand_aliases": ["TB", "Test B"],
        "brand_identity": "AI内容生产",
        "tone": "professional",
        "cta_principles": [
            "Include clear call-to-action in every piece",
            "Link to product demo page",
            "Use action verbs: 立即体验, 免费试用",
        ],
        "blocked_words": ["竞品A", "竞品B"],
    }


@pytest.fixture()
def sample_source_data() -> dict[str, Any]:
    """Synthetic source data for fact-check gate."""
    return {
        "url": "https://example.com/ai-trends-2025",
        "published_date": "2025-06-01T00:00:00+00:00",
        "key_numbers": {
            "market_size": "$150 billion",
            "growth_rate": "35%",
        },
        "entities": ["OpenAI", "Google", "Microsoft"],
        "quotes": [
            "AI will transform every industry",
        ],
        "reference_text": "example.com",
    }


@pytest.fixture()
def sample_gate_context(
    sample_topic: str,
    sample_brand_profile: dict[str, Any],
    sample_source_data: dict[str, Any],
) -> dict[str, Any]:
    """Synthetic gate context suitable for the full pipeline.

    Uses ``_mock_results`` to drive deterministic gate outputs without
    calling any LLM or external service.
    """
    _pass = {"passed": True, "detail": "mock-pass"}
    _all_pass = {
        name: _pass
        for name in [
            # pre-gate
            "topic_not_charity",
            "topic_not_gov_tool",
            "topic_not_investment",
            "topic_not_finance",
            "topic_not_entertainment",
            "topic_length_valid",
            # G0
            "source_trace",
            "number_verification",
            "timeline",
            "quotes",
            "entities",
            # G1
            "overused_adverbs",
            "hollow_intros",
            "vague_subjects",
            "filler_connectors",
            "long_conjunctions",
            "template_conclusions",
            "overacademic_vocabulary",
            "absolute_assertions",
            "repetitive_structures",
            # G2
            "clarity",
            "tone",
            "so_what",
            "evidence",
            "specificity",
            # G3
            "brand_name_present",
            "cta_present",
            "brand_identity",
            "blocked_words_absent",
            "cta_direction_sync",
            "bridge_sentence",
            # G4
            "title_length",
            "digest_length",
            "no_markdown",
            "cover_exists",
            "tag_count",
            "body_image_count",
            "sensitive_words",
            # G5
            "tag_integrity",
            "no_markdown",
            "tag_count",
            # V0
            "lint_errors",
            "lint_warnings",
            "syntax_valid",
            # V1
            "mid_frame_valid",
            "end_silence_valid",
            "all_entries_passed",
            "red_line_6",
            # V2
            "whisper_transcription",
            "transcription_length",
            "md5_integrity",
            "red_line_7",
            # V3
            "keyword_coverage",
            "source_alignment",
            "no_hallucination",
            # V4
            "voice_id_match",
            "speaking_rate",
            "voice_consistency",
            # V5
            "whisper_vs_srt_diff",
            "srt_not_empty",
            "whisper_not_empty",
            # V6
            "subtitle_region_brightness",
            "subtitle_region_contrast",
            "subtitle_visible",
            "red_line_5",
            # V7
            "file_exists",
            "file_size_valid",
            "md5_verified",
            "whisper_full",
            "format_valid",
            "duration_valid",
            # L1
            "topic_present",
            "content_present",
            "media_paths_valid",
            "platform_valid",
            "version_valid",
            "timestamp_valid",
            # L2
            "archive_status",
            "force_flag",
            "archive_path_exists",
            "archive_metadata_complete",
            "archive_version_valid",
            "output_directory_exists",
            # L3
            "all_platforms_present",
            "no_platform_splitting",
            "material_integrity",
            "cross_platform_consistency",
            "format_completeness",
            "metadata_integrity",
        ]
    }

    return {
        # Shared
        "topic": sample_topic,
        "content": (
            "TestBrand delivers AI内容生产 solutions. "
            "立即体验 our platform for free. "
            "Contact us to learn more about how we can help."
        ),
        "brand_profile": sample_brand_profile,
        "source_data": sample_source_data,
        "_mock_results": _all_pass,
        "decision_mode": "build",
        # pre-gate
        # (topic is already set above)
        # G4 — WeChat checklist
        "title": "AI趋势",
        "digest": "AI trends 2025 overview",
        "cover_image": "https://example.com/cover.jpg",
        "tags": ["AI", "tech", "trends", "2025", "innovation"],
        "body_images": [
            "<img src='a.jpg'>",
            "<img src='b.jpg'>",
            "<img src='c.jpg'>",
            "<img src='d.jpg'>",
        ],
        # G5 — HTML hard
        # (content and tags already set)
        # V0 — Lint
        "lint_result": {"errors": 0, "warnings": 0, "syntax_ok": True},
        # V1 — Vision QA
        "entries": [
            {
                "mid_frame_path": f"/synthetic/frame_{i}.png",
                "end_silence_frame_path": f"/synthetic/end_{i}.png",
                "qa_passed": True,
                "checked": True,
            }
            for i in range(5)
        ],
        # V2 — Pre-send whisper
        "transcription": "Full audio transcription text for testing purposes.",
        "audio_path": "/synthetic/test_audio.mp3",
        "expected_md5": "",
        "full_audio": True,
        # V3 — Content semantic
        "source_keywords": ["AI", "technology", "trends", "2025", "production"],
        "content_keywords": ["AI", "technology", "trends", "2025", "production"],
        "source_texts": [
            "Source 1 about AI trends in 2025.",
            "Source 2 about content production.",
            "Source 3 about technology advances.",
        ],
        # V4 — TTS brand asset
        "voice_id": "brand_voice_001",
        "expected_voice_id": "brand_voice_001",
        "speaking_rate": 1.0,
        "segments": [
            {"voice_params": {"pitch": 0, "rate": 1.0}},
            {"voice_params": {"pitch": 0, "rate": 1.0}},
        ],
        # V5 — MP3 vs SRT
        "whisper_text": "Hello world, this is a test transcription.",
        "srt_text": (
            "1\n00:00:00,000 --> 00:00:02,000\nHello world, this is a test transcription.\n"
        ),
        # V6 — Subtitle render
        "avg_brightness": 128,
        "contrast": 150,
        "opacity": 1.0,
        "pixel_valid": True,
        # V7 — 6-step hard
        "required_files": [],
        "file_sizes": {},
        "md5_records": {},
        "whisper_full_audio": True,
        "actual_format": "mp4",
        "expected_format": "mp4",
        "actual_duration": 120.0,
        "expected_duration_min": 60.0,
        "expected_duration_max": 180.0,
        # L1 — Publish log schema
        "publish_log": {
            "topic": sample_topic,
            "content": "Test article content for publish log.",
            "media_paths": ["/synthetic/output/video.mp4"],
            "platform": "wechat",
            "version": "1.0",
            "created_at": "2025-06-01T12:00:00",
        },
        # L2 — Archive validation
        "archive_status": "published",
        "force": True,
        "archive_path": "/synthetic/archive.zip",
        "archive_metadata": {
            "title": "AI Trends 2025",
            "platform": "wechat",
            "created_at": "2025-06-01T12:00:00",
        },
        "output_dir": "/synthetic/output",
        # L3 — Platform integrity
        "platforms": ["wechat", "weibo"],
        "expected_platforms": ["wechat", "weibo"],
        "unified_content": "Unified content body for all platforms.",
        "media_files": [],
        "file_paths": [],
        "formats": ["mp4", "txt", "json"],
        "required_formats": ["mp4", "txt", "json"],
    }


# ---------------------------------------------------------------------------
# LLM mock fixture for LLM-driven gate tests (G0/G2)
# ---------------------------------------------------------------------------


@pytest.fixture()
def llm_mock() -> dict[str, Any]:
    """Fixture providing LLM mock helpers for gate tests.

    Returns a dict with three keys:

    ``response``
        :func:`tests.mock_llm.mock_llm_response` — mock LLM to return a
        given Pydantic model instance.
    ``failure``
        :func:`tests.mock_llm.mock_llm_failure` — simulate LLM API
        failure to force deterministic fallback.
    ``assert_called``
        :func:`tests.mock_llm.assert_llm_called` — assert the LLM was
        called an expected number of times.

    Example
    -------
    >>> def test_my_gate(llm_mock):
    ...     from automedia.gates.llm_helpers import G0CheckResult
    ...     data = G0CheckResult(passed=True, issues=[])
    ...     with llm_mock["response"](data):
    ...         # gate code that calls llm_complete_structured_safe
    ...         pass
    """
    from tests.mock_llm import (
        assert_llm_called,
        mock_llm_failure,
        mock_llm_response,
    )

    return {
        "response": mock_llm_response,
        "failure": mock_llm_failure,
        "assert_called": assert_llm_called,
    }
