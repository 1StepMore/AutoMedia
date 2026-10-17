"""Deterministic tests for tolerant LLM JSON parsing (issue #221).

No network: the LLM is faked by patching the low-level completion helpers.
Covers text-level repair, field-level salvage, the single repair call, and
the fast path (valid JSON must not trigger any repair).
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from pydantic import BaseModel, Field, ValidationError

from automedia.core import llm_client as llm_mod
from automedia.core.llm_client import (
    LLMError,
    _repair_json_text,
    _salvage_fields,
    llm_complete_structured_safe,
)


class _Score(BaseModel):
    relevance_score: float
    reasoning: str = ""


class _OptionalScore(BaseModel):
    relevance_score: float | None = None
    reasoning: str = ""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [k for k in os.environ if k.startswith("AUTOMEDIA_")]:
        monkeypatch.delenv(key, raising=False)
    llm_mod._provider_no_beta_api = {}


def _config() -> dict[str, Any]:
    return {
        "llm": {
            "text_generation": {
                "provider": "test-provider",
                "model": "test-model",
                "api_key": "sk-test",
                "base_url": "https://api.test.com/v1",
            }
        }
    }


def _chat_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage = None
    return response


def _patch_chat_with(contents: list[str]):
    """Patch the low-level chat call to return *contents* in order."""
    return patch.object(
        llm_mod,
        "_llm_chat_completion_with_retry",
        side_effect=[_chat_response(c) for c in contents],
    )


# ---------------------------------------------------------------------------
# A. Text-level repair
# ---------------------------------------------------------------------------


class TestRepairJsonText:
    def test_bare_identifier_value_becomes_null(self) -> None:
        assert _repair_json_text('{"relevance_score": wiggle}') == '{"relevance_score": null}'

    def test_trailing_comma_removed(self) -> None:
        import json

        assert json.loads(_repair_json_text('{"a": 1,}')) == {"a": 1}
        assert json.loads(_repair_json_text("[1, 2,]")) == [1, 2]

    def test_single_quotes_converted(self) -> None:
        import json

        assert json.loads(_repair_json_text("{'a': 'b'}")) == {"a": "b"}

    def test_fence_and_prose_stripped(self) -> None:
        import json

        wrapped = 'Here you go:\n```json\n{"a": 1}\n```\nHope that helps!'
        assert json.loads(_repair_json_text(wrapped)) == {"a": 1}

    def test_nan_and_infinity_become_null(self) -> None:
        import json

        assert json.loads(_repair_json_text('{"a": NaN, "b": Infinity}')) == {
            "a": None,
            "b": None,
        }

    def test_percent_string_is_untouched(self) -> None:
        import json

        assert json.loads(_repair_json_text('{"a": "30%"}')) == {"a": "30%"}

    def test_leading_plus_number_normalised(self) -> None:
        import json

        assert json.loads(_repair_json_text('{"a": +5}')) == {"a": 5}

    def test_repair_is_idempotent(self) -> None:
        once = _repair_json_text('{"relevance_score": wiggle,}')
        assert _repair_json_text(once) == once

    def test_keywords_and_strings_preserved(self) -> None:
        import json

        text = '{"a": true, "b": false, "c": null, "d": "a, } b"}'
        assert json.loads(_repair_json_text(text)) == {
            "a": True,
            "b": False,
            "c": None,
            "d": "a, } b",
        }


# ---------------------------------------------------------------------------
# B. Field-level salvage
# ---------------------------------------------------------------------------


class TestSalvageFields:
    def test_required_bad_field_is_dropped(self) -> None:
        payload, invalid = _salvage_fields(_Score, {"relevance_score": "wiggle"})
        assert invalid == ["relevance_score"]
        assert "relevance_score" not in payload

    def test_optional_bad_field_is_nulled(self) -> None:
        payload, invalid = _salvage_fields(_OptionalScore, {"relevance_score": "wiggle"})
        assert invalid == ["relevance_score"]
        assert payload["relevance_score"] is None

    def test_valid_payload_unchanged(self) -> None:
        payload, invalid = _salvage_fields(_Score, {"relevance_score": 0.5})
        assert invalid == []
        assert payload == {"relevance_score": 0.5}


# ---------------------------------------------------------------------------
# C. End-to-end fallback path
# ---------------------------------------------------------------------------


class TestFallbackRepairFlow:
    @patch.object(llm_mod, "_llm_structured_completion_with_retry")
    @patch.object(llm_mod, "_build_client")
    def test_valid_json_fast_path_no_repair(
        self, mock_build: MagicMock, mock_structured: MagicMock
    ) -> None:
        mock_build.return_value = MagicMock()
        mock_structured.side_effect = AttributeError("no beta API")
        good = '{"relevance_score": 0.8, "reasoning": "ok"}'
        with (
            _patch_chat_with([good]) as chat,
            patch.object(llm_mod, "_attempt_structured_repair") as repair,
        ):
            result = llm_complete_structured_safe(
                "rate this", response_format=_Score, config=_config()
            )
        assert result.relevance_score == 0.8
        assert chat.call_count == 1
        repair.assert_not_called()

    @patch.object(llm_mod, "_llm_structured_completion_with_retry")
    @patch.object(llm_mod, "_build_client")
    def test_bare_identifier_triggers_exactly_one_repair(
        self, mock_build: MagicMock, mock_structured: MagicMock
    ) -> None:
        mock_build.return_value = MagicMock()
        mock_structured.side_effect = AttributeError("no beta API")
        bad = '{"relevance_score": wiggle}'
        with (
            _patch_chat_with([bad]),
            patch.object(
                llm_mod,
                "_attempt_structured_repair",
                return_value='{"relevance_score": 0.9, "reasoning": "repaired"}',
            ) as repair,
        ):
            result = llm_complete_structured_safe(
                "rate this", response_format=_Score, config=_config()
            )
        assert result.relevance_score == 0.9
        assert repair.call_count == 1

    @patch.object(llm_mod, "_llm_structured_completion_with_retry")
    @patch.object(llm_mod, "_build_client")
    def test_repair_call_flows_through_same_provider(
        self, mock_build: MagicMock, mock_structured: MagicMock
    ) -> None:
        mock_build.return_value = MagicMock()
        mock_structured.side_effect = AttributeError("no beta API")
        bad = '{"relevance_score": wiggle}'
        good = '{"relevance_score": 0.7}'
        with _patch_chat_with([bad, good]) as chat:
            result = llm_complete_structured_safe(
                "rate this", response_format=_Score, config=_config()
            )
        assert result.relevance_score == 0.7
        assert chat.call_count == 2

    @patch.object(llm_mod, "_llm_structured_completion_with_retry")
    @patch.object(llm_mod, "_build_client")
    def test_two_bad_responses_raise_with_field_name(
        self, mock_build: MagicMock, mock_structured: MagicMock
    ) -> None:
        mock_build.return_value = MagicMock()
        mock_structured.side_effect = AttributeError("no beta API")
        bad = '{"relevance_score": wiggle}'
        with _patch_chat_with([bad, bad]), pytest.raises(LLMError, match="relevance_score"):
            llm_complete_structured_safe("rate this", response_format=_Score, config=_config())

    @patch.object(llm_mod, "_llm_structured_completion_with_retry")
    @patch.object(llm_mod, "_build_client")
    def test_beta_fenced_content_uses_tolerance(
        self, mock_build: MagicMock, mock_structured: MagicMock
    ) -> None:
        mock_build.return_value = MagicMock()
        beta = MagicMock()
        beta.choices = [MagicMock()]
        beta.usage = None
        type(beta.choices[0].message).parsed = PropertyMock(
            side_effect=ValidationError.from_exception_data("_Score", line_errors=[])
        )
        beta.choices[0].message.content = "```json\n{'relevance_score': NaN}\n```"
        mock_structured.return_value = beta
        result = llm_complete_structured_safe(
            "rate this", response_format=_OptionalScore, config=_config()
        )
        assert isinstance(result, _OptionalScore)


# ---------------------------------------------------------------------------
# Required-field helper sanity (issue #221 acceptance #1)
# ---------------------------------------------------------------------------


class TestRequiredFieldMissing:
    def test_missing_required_field_after_salvage_fails(self) -> None:
        from automedia.core.llm_client import _tolerant_validate

        instance, invalid, detail = _tolerant_validate(_Score, '{"relevance_score": wiggle}')
        assert instance is None
        assert "relevance_score" in invalid
        assert detail is not None

    def test_extra_allow_model_records_invalid_fields(self) -> None:
        from pydantic import ConfigDict

        from automedia.core.llm_client import _tolerant_validate

        class _Extra(BaseModel):
            model_config = ConfigDict(extra="allow")
            relevance_score: float = Field(default=0.0)

        instance, invalid, _detail = _tolerant_validate(
            _Extra, '{"relevance_score": "bad", "reasoning": "x"}'
        )
        assert instance is not None
        assert invalid == ["relevance_score"]
        assert instance._invalid_fields == ["relevance_score"]
