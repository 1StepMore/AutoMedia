"""G0 one-shot rewrite emission + fail-closed behavior (issue #219).

Drives the real :class:`G0FactCheck` with the LLM mocked at the shared seam
(``automedia.core.llm_client._structured_completion_with_fallback``) so the
rewrite path is exercised exactly as the frozen regression driver drives it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from automedia.gates.fact_check import G0FactCheck
from automedia.gates.llm_helpers import G0CheckResult, G0RewriteResult

_PATCH_COMPLETION = "automedia.core.llm_client._structured_completion_with_fallback"
_PATCH_FAKE = "automedia.core.llm_client._is_fake_mode"
_PATCH_SPECS = "automedia.core.llm_client._iter_provider_specs"

_SOURCE_DATA: dict[str, Any] = {
    "url": "https://example.com/source-article",
    "published_date": "2024-06-01T00:00:00",
    "key_numbers": {"revenue": "42"},
    "entities": [],
    "quotes": [],
}

_FAILING = G0CheckResult(
    passed=False,
    issues=[
        "unsourced number '30%' in sentence: 「点击率高 30%」 — no citation in the source material",
    ],
    confidence=0.2,
)


def _context(
    *,
    content: str = "据我们的渠道观察，这款产品的点击率高 30%，整体转化表现稳定。\n",
    source_data: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "topic": "渠道观察",
        "content": content,
        "source_data": _SOURCE_DATA if source_data is None else source_data,
        "config": {"enable_llm": True} if config is None else config,
    }


@contextmanager
def _llm(
    check_results: list[G0CheckResult],
    reward: G0RewriteResult | None = None,
    *,
    rewrite_raises: bool = False,
) -> Iterator[dict[str, int]]:
    """Patch the shared structured-completion seam with a call dispatcher.

    ``G0CheckResult`` requests are answered in order from *check_results*;
    every other ``response_format`` is the rewrite request.
    """
    calls = {"check": 0, "rewrite": 0}

    def _dispatch(_prompt: str, *, response_format: type[Any], **_kwargs: object) -> object:
        if response_format is G0CheckResult:
            index = min(calls["check"], len(check_results) - 1)
            calls["check"] += 1
            return check_results[index]
        calls["rewrite"] += 1
        if rewrite_raises:
            raise RuntimeError("rewrite provider failed (simulated)")
        return reward if reward is not None else G0RewriteResult()

    with (
        patch(_PATCH_COMPLETION, side_effect=_dispatch),
        patch(_PATCH_FAKE, return_value=False),
        patch(_PATCH_SPECS, return_value=[]),
    ):
        yield calls


class TestG0RewriteEmission:
    """The first failing attempt emits exactly one rewrite."""

    def test_failing_check_sets_error_and_emits_one_rewrite(self) -> None:
        ctx = _context()
        with _llm([_FAILING], G0RewriteResult(rewritten_content="fixed copy")) as calls:
            result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        assert isinstance(result["error"], str) and result["error"].strip()
        assert "30%" in result["error"]
        assert result["modified_content"] == "fixed copy"
        assert ctx["_g0_rewrite_attempted"] is True
        assert calls["check"] == 1
        assert calls["rewrite"] == 1

    def test_second_failure_does_not_re_emit(self) -> None:
        ctx = _context()
        still_failing = G0CheckResult(
            passed=False,
            issues=["unsourced number '30%' still present after the rewrite"],
            confidence=0.2,
        )
        reward = G0RewriteResult(rewritten_content="fixed copy")
        with _llm([_FAILING, still_failing], reward) as calls:
            first = G0FactCheck().execute(ctx)
            again = G0FactCheck().execute(ctx)

        assert first.get("modified_content") == "fixed copy"
        assert "modified_content" not in again
        assert again["passed"] is False
        assert again["error"]
        assert calls["rewrite"] == 1
        assert calls["check"] == 2

    def test_rewrite_raises_is_fail_closed(self) -> None:
        ctx = _context()
        with _llm([_FAILING], rewrite_raises=True):
            result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        assert result["error"]
        assert "modified_content" not in result
        assert ctx["_g0_rewrite_attempted"] is True

    def test_empty_rewrite_is_fail_closed(self) -> None:
        ctx = _context()
        with _llm([_FAILING], G0RewriteResult(rewritten_content="   ")):
            result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        assert result["error"]
        assert "modified_content" not in result

    def test_pass_keeps_error_none_and_no_rewrite(self) -> None:
        ctx = _context()
        with _llm([G0CheckResult(passed=True, issues=[], confidence=0.95)]) as calls:
            result = G0FactCheck().execute(ctx)

        assert result["passed"] is True
        assert result["error"] is None
        assert "modified_content" not in result
        assert calls["rewrite"] == 0

    def test_enable_llm_false_fails_without_rewrite_attempt(self) -> None:
        ctx = _context(
            content="Some content without any domain reference.",
            source_data={
                "url": "https://trusted-source.org/article",
                "published_date": "",
                "key_numbers": {},
                "entities": [],
                "quotes": [],
            },
            config={"enable_llm": False},
        )
        with _llm([]) as calls:
            result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        assert result["error"]
        assert "modified_content" not in result
        assert "_g0_rewrite_attempted" not in ctx
        assert calls["check"] == 0
        assert calls["rewrite"] == 0


class TestG0StructuredReason:
    """Failing checks carry readable sentence/number/citation detail."""

    def test_failing_check_carries_number_hint(self) -> None:
        ctx = _context()
        with _llm([_FAILING], G0RewriteResult(rewritten_content="fixed copy")):
            result = G0FactCheck().execute(ctx)

        failing = [c for c in result["checks"] if not c["passed"]]
        assert failing
        assert any("30%" in c.get("number", "") for c in failing)

    def test_structured_issues_override_heuristics(self) -> None:
        ctx = _context()
        structured = G0CheckResult(
            passed=False,
            issues=["unsourced figure"],
            confidence=0.2,
            structured_issues=[
                {"sentence": "点击率高 30%", "number": "30%", "missing_citation": True},
            ],
        )
        with _llm([structured], G0RewriteResult(rewritten_content="fixed copy")):
            result = G0FactCheck().execute(ctx)

        failing = [c for c in result["checks"] if not c["passed"]]
        assert failing[0].get("sentence") == "点击率高 30%"
        assert failing[0].get("number") == "30%"
        assert failing[0].get("missing_citation") is True
