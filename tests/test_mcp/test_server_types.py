"""Tests for MCP server type aliases (server_types.py).

Covers NonEmptyStr, PipelineMode, CronExpression, ProjectStatusFilter,
EngineModality, and ResearchPattern type aliases defined in
``automedia.mcp.server_types``.

All tests use synthetic data — zero production data.
"""

from __future__ import annotations

import re
from typing import get_args, get_origin

import pytest

from automedia.mcp.server_types import (
    CronExpression,
    EngineModality,
    GateName,
    NonEmptyStr,
    PipelineMode,
    ProjectStatusFilter,
    ResearchPattern,
    RetryLevel,
    TopicStatus,
)

# ---------------------------------------------------------------------------
# NonEmptyStr
# ---------------------------------------------------------------------------


class TestNonEmptyStr:
    """Tests for the NonEmptyStr annotated type.

    NonEmptyStr is defined as ``Annotated[str, Field(min_length=1)]``.
    Since Pydantic Field metadata is introspectable but does not enforce at
    the type-hint level, we test the constraint via a helper that simulates
    Pydantic validation.
    """

    def test_is_annotated_type(self) -> None:
        """NonEmptyStr is an Annotated type originating from str."""
        origin = get_origin(NonEmptyStr)
        assert origin is not None, "NonEmptyStr should be a generic alias"
        # The origin of Annotated[str, ...] is not directly str, but we
        # can check the first argument
        args = get_args(NonEmptyStr)
        assert args[0] is str, "NonEmptyStr's base type should be str"

    def test_rejects_empty_string_via_pydantic(self) -> None:
        """NonEmptyStr raises a validation error for empty strings.

        We test this via a small Pydantic model that uses NonEmptyStr.
        """
        from pydantic import BaseModel, ValidationError

        class _TestModel(BaseModel):
            value: NonEmptyStr  # type: ignore[valid-type]

        # Valid: non-empty string
        m = _TestModel(value="hello")
        assert m.value == "hello"

        # Invalid: empty string
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            _ = _TestModel(value="")  # noqa: F841

    def test_accepts_non_empty_string(self) -> None:
        """NonEmptyStr accepts any non-empty string via Pydantic."""
        from pydantic import BaseModel

        class _TestModel(BaseModel):
            value: NonEmptyStr  # type: ignore[valid-type]

        for valid_input in ("x", "hello world", "a" * 1000, "测试", "123", "_"):
            m = _TestModel(value=valid_input)
            assert m.value == valid_input


# ---------------------------------------------------------------------------
# PipelineMode
# ---------------------------------------------------------------------------


class TestPipelineMode:
    """Tests for the PipelineMode Literal type."""

    def test_is_literal_type(self) -> None:
        """PipelineMode is a Literal type."""
        origin = get_origin(PipelineMode)
        assert origin is not None

    def test_includes_all_valid_modes(self) -> None:
        """PipelineMode includes all known pipeline modes."""
        args = get_args(PipelineMode)
        expected = {
            "auto",
            "text_only",
            "text_with_cover",
            "video_only",
            "qa_only",
            "image-carousel",
            "social-thread",
            "short-video",
        }
        assert set(args) == expected

    def test_rejects_invalid_mode_via_validation(self) -> None:
        """Invalid pipeline modes are rejected by the runtime validation.

        The type hint alone does not enforce at runtime, but the
        run_pipeline function validates against VALID_MODES.
        """
        from automedia.pipelines.runner import VALID_MODES

        invalid_modes = ["invalid", "auto-mode", "textonly", "", "full", "Fast"]
        for mode in invalid_modes:
            assert mode not in VALID_MODES, f"{mode!r} should not be a valid mode"


# ---------------------------------------------------------------------------
# CronExpression
# ---------------------------------------------------------------------------


class TestCronExpression:
    """Tests for the CronExpression annotated type.

    CronExpression enforces a 5-field cron expression
    via Pydantic's pattern validation.
    """

    def test_is_annotated_type(self) -> None:
        """CronExpression is an Annotated type."""
        origin = get_origin(CronExpression)
        assert origin is not None
        args = get_args(CronExpression)
        assert args[0] is str

    def test_pattern_rejects_invalid_expressions(self) -> None:
        """The underlying regex pattern only matches 5-field expressions."""
        pattern = r"^(\S+\s+){4}\S+$"
        valid = [
            "0 0 * * *",
            "*/5 * * * *",
            "30 6 * * 1-5",
            "0 0 1 1 *",
            "0,15 0 * * *",
        ]
        invalid = [
            "",
            "0 0 * *",  # 4 fields
            "0 0 * * * *",  # 6 fields
            "invalid",
        ]
        for expr in valid:
            assert re.match(pattern, expr), f"{expr!r} should match cron pattern"
        for expr in invalid:
            assert not re.match(pattern, expr), f"{expr!r} should NOT match cron pattern"

    def test_rejects_invalid_via_pydantic(self) -> None:
        """CronExpression rejects invalid expressions via Pydantic validation."""
        from pydantic import BaseModel, ValidationError

        class _TestModel(BaseModel):
            value: CronExpression  # type: ignore[valid-type]

        # Valid
        m = _TestModel(value="0 6 * * *")
        assert m.value == "0 6 * * *"

        # Invalid: too few fields
        with pytest.raises(ValidationError):
            _ = _TestModel(value="0 6 * *")  # noqa: F841

        # Invalid: empty
        with pytest.raises(ValidationError):
            _ = _TestModel(value="")  # noqa: F841

    def test_accepts_valid_expressions(self) -> None:
        """CronExpression accepts common valid cron expressions."""
        from pydantic import BaseModel

        class _TestModel(BaseModel):
            value: CronExpression  # type: ignore[valid-type]

        for expr in (
            "0 0 * * *",
            "*/15 * * * *",
            "0 9-17 * * 1-5",
            "30 4 * * 0",
            "0 0 1 1 *",
        ):
            m = _TestModel(value=expr)
            assert m.value == expr


# ---------------------------------------------------------------------------
# ProjectStatusFilter
# ---------------------------------------------------------------------------


class TestProjectStatusFilter:
    """Tests for the ProjectStatusFilter Literal type."""

    def test_is_literal_type(self) -> None:
        """ProjectStatusFilter is a Literal type."""
        origin = get_origin(ProjectStatusFilter)
        assert origin is not None

    def test_includes_expected_values(self) -> None:
        """ProjectStatusFilter includes all expected filter values."""
        args = get_args(ProjectStatusFilter)
        expected = {"published", "archived", "failed", ""}
        assert set(args) == expected

    def test_rejects_invalid_values(self) -> None:
        """Invalid status filter values are rejected at type-check time.

        At runtime, the function body should also reject invalid values.
        We verify that the Literal restricts the expected set.
        """
        args = get_args(ProjectStatusFilter)
        for invalid in ("draft", "pending", "all", "deleted", "unknown"):
            assert invalid not in args, f"{invalid!r} should not be a valid status filter"


# ---------------------------------------------------------------------------
# EngineModality
# ---------------------------------------------------------------------------


class TestEngineModality:
    """Tests for the EngineModality Literal type."""

    def test_is_literal_type(self) -> None:
        """EngineModality is a Literal type."""
        origin = get_origin(EngineModality)
        assert origin is not None

    def test_includes_expected_values(self) -> None:
        """EngineModality includes all expected modality values."""
        args = get_args(EngineModality)
        expected = {"tts", "asr", "image", "video"}
        assert set(args) == expected

    def test_rejects_invalid_values(self) -> None:
        """Invalid modality values are not part of the Literal args."""
        args = get_args(EngineModality)
        for invalid in ("audio", "text", "ocr", "translation"):
            assert invalid not in args, f"{invalid!r} should not be a valid modality"

    def test_accepts_valid_values_as_literal_args(self) -> None:
        """Valid modality values are part of the EngineModality Literal args."""
        args = get_args(EngineModality)
        for valid in ("tts", "asr", "image", "video"):
            assert valid in args, f"{valid!r} should be a valid modality"


# ---------------------------------------------------------------------------
# ResearchPattern
# ---------------------------------------------------------------------------


class TestResearchPattern:
    """Tests for the ResearchPattern Literal type."""

    def test_is_literal_type(self) -> None:
        """ResearchPattern is a Literal type."""
        origin = get_origin(ResearchPattern)
        assert origin is not None

    def test_includes_a_and_b(self) -> None:
        """ResearchPattern includes both 'a' and 'b' patterns."""
        args = get_args(ResearchPattern)
        assert "a" in args
        assert "b" in args
        assert len(args) == 2

    def test_rejects_other_values(self) -> None:
        """ResearchPattern rejects values other than 'a' and 'b'."""
        args = get_args(ResearchPattern)
        for invalid in ("c", "default", "deep", "", "1", "trending"):
            assert invalid not in args


# ---------------------------------------------------------------------------
# TopicStatus
# ---------------------------------------------------------------------------


class TestTopicStatus:
    """Tests for the TopicStatus Literal type."""

    def test_is_literal_type(self) -> None:
        """TopicStatus is a Literal type."""
        origin = get_origin(TopicStatus)
        assert origin is not None

    def test_includes_expected_values(self) -> None:
        """TopicStatus includes all expected topic status values."""
        args = get_args(TopicStatus)
        expected = {"pending", "selected", "published", "archived"}
        assert set(args) == expected


# ---------------------------------------------------------------------------
# GateName
# ---------------------------------------------------------------------------


class TestGateName:
    """Tests for the GateName Literal type."""

    def test_is_literal_type(self) -> None:
        """GateName is a Literal type."""
        origin = get_origin(GateName)
        assert origin is not None

    def test_includes_all_known_gates(self) -> None:
        """GateName includes all valid gate names."""
        args = get_args(GateName)
        expected = {
            "pre-gate",
            "CW",
            "G0",
            "G1",
            "G2",
            "G3",
            "G4",
            "G5",
            "V0",
            "V1",
            "V2",
            "V3",
            "V4",
            "V5",
            "V6",
            "V7",
            "H0",
            "L1",
            "L2",
            "L3",
            "L4",
        }
        assert set(args) == expected
        assert len(args) == len(expected)


# ---------------------------------------------------------------------------
# RetryLevel
# ---------------------------------------------------------------------------


class TestRetryLevel:
    """Tests for the RetryLevel Literal type."""

    def test_is_literal_type(self) -> None:
        """RetryLevel is a Literal type."""
        origin = get_origin(RetryLevel)
        assert origin is not None

    def test_includes_expected_values(self) -> None:
        """RetryLevel includes quality, tenacity, and manual."""
        args = get_args(RetryLevel)
        expected = {"quality", "tenacity", "manual"}
        assert set(args) == expected


# ---------------------------------------------------------------------------
# Module __all__
# ---------------------------------------------------------------------------


class TestModuleAll:
    """Tests for the server_types module's __all__ export list."""

    def test_all_exports_match_definitions(self) -> None:
        """The __all__ list correctly exports all public type aliases."""
        from automedia.mcp import server_types

        expected = {
            "PipelineMode",
            "ResearchPattern",
            "EngineModality",
            "TopicStatus",
            "GateName",
            "RetryLevel",
            "NonEmptyStr",
            "CronExpression",
            "ProjectStatusFilter",
        }
        assert set(server_types.__all__) == expected
