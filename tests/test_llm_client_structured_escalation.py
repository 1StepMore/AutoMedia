"""Structured-output budget escalation (#625).

A reasoning model shares one ``max_tokens`` budget between its thinking trace
and the payload.  On the structured path that surfaces as
``LengthFinishReasonError`` from the beta parse endpoint, or as JSON cut
mid-string once the manual ``json_object`` fallback takes over with
``completion_tokens`` pinned to ``max_tokens``.  #624 fixed the plain-text path
only, so ``llm_complete_structured_safe`` kept re-asking every provider in the
chain with the same thin budget and reported "0 provider(s) remaining".

These tests pin the escalation policy: exactly one retry at 2x (capped at
16000), and only for truncation — any other failure keeps the configured
budget.  Confidence: mock (no network); the real-model acceptance run lives in
the PR body.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from automedia.core.llm_client import (
    LLMError,
    get_last_structured_provenance,
    llm_complete_structured_safe,
)

openai = pytest.importorskip("openai")


class _SpotCheck(BaseModel):
    """Minimal structured-output schema standing in for ContentQualityOutput."""

    score: float
    summary: str


TRUNCATED_JSON = '{"score": 0.8, "summary": "the evalu'


@pytest.fixture(autouse=True)
def _isolate_llm_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear AUTOMEDIA_* env, the beta-support cache and thread provenance."""
    from automedia.core import llm_client as llm_client_module

    for key in [k for k in os.environ if k.startswith("AUTOMEDIA_")]:
        monkeypatch.delenv(key, raising=False)
    llm_client_module._provider_no_beta_api = {}
    llm_client_module._structured_provenance.last = {}


def _config(max_tokens: int, timeout: float | None = None) -> dict[str, Any]:
    """Build a single-provider config for the structured path."""
    block: dict[str, Any] = {
        "provider": "test-provider",
        "model": "reasoning-model",
        "api_key": "sk-test",
        "base_url": "https://api.test.com/v1",
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    if timeout is not None:
        block["timeout"] = timeout
    return {"llm": {"text_generation": block}}


def _usage(completion_tokens: int) -> SimpleNamespace:
    """Build an OpenAI-shaped usage block."""
    return SimpleNamespace(
        prompt_tokens=1449,
        completion_tokens=completion_tokens,
        total_tokens=1449 + completion_tokens,
    )


def _chat_response(content: str, *, finish_reason: str | None, completion_tokens: int) -> MagicMock:
    """Build a chat-completion response (the manual json_object path)."""
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason
    response.choices = [choice]
    response.usage = _usage(completion_tokens)
    return response


def _parsed_response(parsed: BaseModel, *, completion_tokens: int = 320) -> MagicMock:
    """Build a beta ``parse`` response carrying an already-parsed model."""
    response = MagicMock()
    choice = MagicMock()
    choice.message.parsed = parsed
    choice.message.content = '{"score": 0.8, "summary": "ok"}'
    choice.finish_reason = "stop"
    response.choices = [choice]
    response.usage = _usage(completion_tokens)
    return response


def _length_finish_error() -> BaseException:
    """Build the SDK's LengthFinishReasonError for a 2048-token truncation."""
    completion = SimpleNamespace(usage=_usage(2048))
    return openai.LengthFinishReasonError(completion=completion)


class TestStructuredBudgetEscalation:
    """Truncated structured attempts escalate once; other failures do not."""

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_truncation_escalates_budget_once_and_succeeds(
        self,
        mock_build: MagicMock,
        mock_struct: MagicMock,
        mock_chat: MagicMock,
    ) -> None:
        """LengthFinishReasonError + truncated JSON => one 2x retry that succeeds."""
        import automedia.core.llm_client as llm_client_module

        mock_build.return_value = MagicMock()
        # Attempt 1 (2048): beta parse is cut off, the json_object fallback comes
        # back as JSON truncated mid-string with the budget fully consumed.
        # Attempt 2 (4096): the beta path answers and parses natively.
        mock_struct.side_effect = [
            _length_finish_error(),
            _parsed_response(_SpotCheck(score=0.8, summary="ok")),
        ]
        mock_chat.return_value = _chat_response(
            TRUNCATED_JSON, finish_reason="length", completion_tokens=2048
        )

        result = llm_complete_structured_safe(
            "evaluate this draft",
            response_format=_SpotCheck,
            config=_config(max_tokens=2048),
        )

        assert isinstance(result, _SpotCheck)
        assert result.score == 0.8
        # Exactly one escalation, 2048 -> 4096, and no third attempt.
        assert mock_struct.call_count == 2
        budgets = [call[1]["max_tokens"] for call in mock_struct.call_args_list]
        assert budgets == [2048, 4096]
        # The repair call is skipped for a truncated payload: re-asking at the
        # same budget cannot terminate the JSON.
        assert mock_chat.call_count == 1
        # No configured timeout => no client widening (request stays as-is).
        mock_build.return_value.with_options.assert_not_called()
        # A budget truncation is not a missing capability: the beta path stays on.
        assert llm_client_module._provider_no_beta_api.get("test-provider") is None
        provenance = get_last_structured_provenance()
        assert provenance["attempt"] == 2
        assert provenance["truncated"] is False
        assert provenance["max_tokens"] == 4096
        assert provenance["provider"] == "test-provider"
        assert provenance["model"] == "reasoning-model"

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_second_truncation_stops_the_ladder(
        self,
        mock_build: MagicMock,
        mock_struct: MagicMock,
        mock_chat: MagicMock,
    ) -> None:
        """Truncated at 2048 *and* at 4096 => stop after the one retry (#625).

        The escalation is a ladder of exactly two rungs.  Removing the
        ``budget >= escalation_target`` guard would otherwise re-enter the
        retry forever, so this case pins the stopping point: two attempts, no
        third, and an attributable error carrying the escalated provenance.
        """
        mock_build.return_value = MagicMock()
        # Both attempts are cut off: attempt 1 at 2048, attempt 2 at 4096.
        mock_struct.side_effect = [_length_finish_error(), _length_finish_error()]
        mock_chat.side_effect = [
            _chat_response(TRUNCATED_JSON, finish_reason="length", completion_tokens=2048),
            _chat_response(TRUNCATED_JSON, finish_reason="length", completion_tokens=4096),
        ]

        with pytest.raises(LLMError) as excinfo:
            llm_complete_structured_safe(
                "evaluate this draft",
                response_format=_SpotCheck,
                config=_config(max_tokens=2048),
            )

        # Exactly two attempts — 2048 then the escalated 4096, never a 4097th call.
        assert mock_struct.call_count == 2
        assert [call[1]["max_tokens"] for call in mock_struct.call_args_list] == [2048, 4096]
        assert mock_chat.call_count == 2
        # The chain error keeps the escalated attempt's provenance.
        error = excinfo.value
        assert error.truncated is True
        assert error.attempt == 2
        assert error.finish_reason == "length"
        assert error.provenance["max_tokens"] == 4096
        assert error.provenance["completion_tokens"] == 4096
        # ...and the message is attributable, not a bare parse error.
        message = str(error)
        assert "truncated by max_tokens" in message
        assert "provider='test-provider'" in message
        assert "model='reasoning-model'" in message
        assert "budget=4096" in message
        assert "finish_reason='length'" in message
        assert "completion_tokens=4096" in message

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_escalated_retry_widens_the_wall_clock(
        self,
        mock_build: MagicMock,
        mock_struct: MagicMock,
        mock_chat: MagicMock,
    ) -> None:
        """The 2x-budget retry runs on a 2x timeout instead of the same clock.

        With the shipped ``max_tokens=2048`` / ``timeout=60`` pair a reasoning
        model already spends nearly the whole timeout, so an escalation on the
        original clock would only turn the truncation into a timeout.
        """
        mock_build.return_value = MagicMock()
        wide_client = mock_build.return_value.with_options.return_value
        mock_struct.side_effect = [
            _length_finish_error(),
            _parsed_response(_SpotCheck(score=0.9, summary="ok")),
        ]
        mock_chat.return_value = _chat_response(
            TRUNCATED_JSON, finish_reason="length", completion_tokens=2048
        )

        result = llm_complete_structured_safe(
            "evaluate this draft",
            response_format=_SpotCheck,
            config=_config(max_tokens=2048, timeout=60),
        )

        assert result.score == 0.9
        mock_build.return_value.with_options.assert_called_once_with(timeout=120.0, max_retries=0)
        # The escalated attempt is the one that runs on the widened client.
        assert mock_struct.call_args_list[0][0][0] is mock_build.return_value
        assert mock_struct.call_args_list[1][0][0] is wide_client

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_non_truncation_failure_keeps_budget(
        self,
        mock_build: MagicMock,
        mock_struct: MagicMock,
        mock_chat: MagicMock,
    ) -> None:
        """A non-truncation parse failure never escalates the budget."""
        import automedia.core.llm_client as llm_client_module

        mock_build.return_value = MagicMock()
        # Provider without a beta endpoint, and a payload that is simply not
        # JSON with the budget nowhere near exhausted.
        mock_struct.side_effect = AttributeError("no beta endpoint")
        mock_chat.return_value = _chat_response(
            "not json at all", finish_reason="stop", completion_tokens=17
        )

        with pytest.raises(LLMError, match="failed for all 1 provider"):
            llm_complete_structured_safe(
                "evaluate this draft",
                response_format=_SpotCheck,
                config=_config(max_tokens=2048),
            )

        assert mock_struct.call_count == 1
        assert {call[1]["max_tokens"] for call in mock_chat.call_args_list} == {2048}
        # The historical repair attempt still runs for a non-truncated failure.
        assert mock_chat.call_count == 2
        # A genuinely absent beta endpoint is still cached as a skip.
        assert llm_client_module._provider_no_beta_api.get("test-provider") is True

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_cap_reached_does_not_retry(
        self,
        mock_build: MagicMock,
        mock_struct: MagicMock,
        mock_chat: MagicMock,
    ) -> None:
        """At the 16000-token cap a truncation is attributable, not retried."""
        mock_build.return_value = MagicMock()
        mock_struct.side_effect = _length_finish_error()
        mock_chat.return_value = _chat_response(
            TRUNCATED_JSON, finish_reason="length", completion_tokens=16000
        )

        with pytest.raises(LLMError, match="truncated") as excinfo:
            llm_complete_structured_safe(
                "evaluate this draft",
                response_format=_SpotCheck,
                config=_config(max_tokens=16000),
            )

        assert mock_struct.call_count == 1
        assert mock_chat.call_count == 1
        error = excinfo.value
        assert error.truncated is True
        assert error.provenance["max_tokens"] == 16000
        assert error.provenance["finish_reason"] == "length"
        assert error.provenance["completion_tokens"] == 16000

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_truncated_but_parseable_result_is_returned(
        self,
        mock_build: MagicMock,
        mock_struct: MagicMock,
        mock_chat: MagicMock,
    ) -> None:
        """A payload that parsed despite finish_reason=length is not escalated."""
        mock_build.return_value = MagicMock()
        mock_struct.side_effect = _length_finish_error()
        mock_chat.return_value = _chat_response(
            '{"score": 0.6, "summary": "usable"}',
            finish_reason="length",
            completion_tokens=2048,
        )

        result = llm_complete_structured_safe(
            "evaluate this draft",
            response_format=_SpotCheck,
            config=_config(max_tokens=2048),
        )

        assert result.summary == "usable"
        assert mock_struct.call_count == 1
        assert mock_chat.call_count == 1
        provenance = get_last_structured_provenance()
        assert provenance["truncated"] is True
        assert provenance["attempt"] == 1
        assert provenance["max_tokens"] == 2048
