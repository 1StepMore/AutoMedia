"""Deterministic hook-claim hedge pass (#598).

The G0 rewrite is an LLM round-trip; this pass guarantees the closed token
list is gone from the flagged sentences, so the engine's retry can converge.
A token with no mapping is never faked away.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.gates.hook_claims_rewrite import (
    HEDGE_MAP,
    hedge_all_hook_claims,
    hedge_hook_claims,
)
from automedia.prompts.hook_claims import HOOK_CLAIMS_BANNED_TOKENS, hook_area_violations

HIT_HOOK = (
    "# 三步写周报，一定轻松\n\n"
    "很多人写周报没章法。\n\n"
    "## 挑重点\n\n"
    "把本周最有价值的三件事挑出来。\n\n"
    "照着做一遍。"
)


def test_hedge_clears_the_flagged_hook() -> None:
    before = hook_area_violations(HIT_HOOK)
    assert {"一定", "轻松"} <= {hit.token for hit in before}

    hedged = hedge_hook_claims(HIT_HOOK)

    assert hook_area_violations(hedged) == []
    assert "# 三步写周报，往往不那么费劲" in hedged


def test_longest_token_wins() -> None:
    content = "# 三步轻松搞定周报\n\n正文。\n\n照着做一遍。"
    hedged = hedge_hook_claims(content)
    assert "不那么费劲地处理" in hedged
    assert "不那么费劲搞定" not in hedged
    assert hook_area_violations(hedged) == []


def test_body_text_is_left_untouched() -> None:
    content = (
        "# 写周报的三个卡点\n\n第一段讲常见误区。\n\n"
        "中间引用团队的话，比如有人把周报叫「保证质量的仪式」。\n\n"
        "最后一行没有违禁词。"
    )
    assert hedge_hook_claims(content) == content


def test_unmapped_token_survives_and_stays_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no mapping the sentence is untouched AND still flagged — no fake pass."""
    from automedia.gates import hook_claims_rewrite as module

    partial = {k: v for k, v in HEDGE_MAP.items() if k != "一定"}
    monkeypatch.setattr(module, "HEDGE_MAP", partial)
    monkeypatch.setattr(module, "_HEDGE_ORDER", tuple(sorted(partial, key=len, reverse=True)))

    content = "# 三步写周报，一定顺利\n\n正文。\n\n照着做一遍。"
    hedged = hedge_hook_claims(content)

    assert hedged == content
    assert {hit.token for hit in hook_area_violations(hedged)} == {"一定"}


def test_tokens_past_the_160_char_cap_are_still_hedged() -> None:
    """``HookClaimHit.text`` is capped at 160 chars; the real failing draft
    (#598) puts both tokens past the cap.  The hedged span must reach them
    without touching the next block."""
    filler = "读者划过信息流时，封面在替文章做最初的自我介绍，" * 6
    first = f"{filler}结论是一定的，过程也是轻松的。"
    body = "正文第一段不能动：一定的轻松只是举例。"
    content = f"# 封面设计如何提升点击率\n\n{first}\n\n{body}\n\n照着自己的封面检查一遍。"

    hedged = hedge_hook_claims(content)

    assert hook_area_violations(hedged) == []
    assert "往往" in hedged and "不那么费劲" in hedged
    assert body in hedged  # the following block is untouched


def test_every_banned_token_has_a_hedge_entry() -> None:
    """The table covers the closed list — drift is caught here, not in prod."""
    assert set(HOOK_CLAIMS_BANNED_TOKENS) <= set(HEDGE_MAP)


class TestHedgeAllHookClaims:
    """Generation-boundary hedge (image-track drafts, no markdown headings)."""

    def test_body_token_is_hedged_too(self) -> None:
        content = (
            "文章封面并不是标题的附属装饰\n"
            "读者在极短时间内决定要不要点进去\n"
            "重点信息保证在小尺寸下依然清晰可辨"
        )
        hedged = hedge_all_hook_claims(content)
        assert "决定" not in hedged and "保证" not in hedged
        assert "影响要不要点进去" in hedged
        assert "注意" in hedged

    def test_no_banned_token_survives_anywhere(self) -> None:
        content = "标题一定轻松\n正文一定轻松，保证学会，一招搞定。"
        hedged = hedge_all_hook_claims(content)
        assert [hit.token for hit in hook_area_violations(hedged)] == []
        for token in HOOK_CLAIMS_BANNED_TOKENS:
            assert token not in hedged

    def test_verb_object_body_phrases_stay_grammatical(self) -> None:
        """「保证＋名词」must not become the adverb「通常＋名词」(#gap2)."""
        hedged = hedge_all_hook_claims("保证清晰度，保证明暗对比。")
        assert "注意清晰度" in hedged
        assert "注意明暗对比" in hedged
        assert "通常" not in hedged

    def test_longer_token_still_wins(self) -> None:
        hedged = hedge_all_hook_claims("三步轻松搞定")
        assert "不那么费劲地处理" in hedged
        assert "搞定" not in hedged

    def test_unmapped_token_is_not_faked_away(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from automedia.gates import hook_claims_rewrite as module

        partial = {k: v for k, v in HEDGE_MAP.items() if k != "一定"}
        monkeypatch.setattr(module, "HEDGE_MAP", partial)
        monkeypatch.setattr(module, "_HEDGE_ORDER", tuple(sorted(partial, key=len, reverse=True)))
        content = "正文里一定会出现这个词"
        assert hedge_all_hook_claims(content) == content

    def test_idempotent_and_empty_safe(self) -> None:
        content = "一定轻松搞定"
        hedged = hedge_all_hook_claims(content)
        assert hedge_all_hook_claims(hedged) == hedged
        assert hedge_all_hook_claims("") == ""


def test_empty_content_is_returned_unchanged() -> None:
    assert hedge_hook_claims("") == ""


def test_repeated_sentence_is_hedged_per_occurrence() -> None:
    """A hit sentence repeated in the original is written back in place."""
    content = "# 标题\n\n一定轻松。\n\n中间。\n\n一定轻松。"
    hedged = hedge_hook_claims(content)
    assert hedged.count("一定") == 0
    assert hedged.count("往往不那么费劲") == 2


def test_module_does_not_touch_the_criteria() -> None:
    """The ban list stays the single source of truth — this pass only reads it."""
    source = Path(__file__).parents[2] / "src" / "automedia" / "prompts" / "hook_claims.py"
    assert "HEDGE_MAP" not in source.read_text(encoding="utf-8")


def test_g0_rewrite_output_is_hedged_before_it_is_returned() -> None:
    """The LLM rewrite still carrying the tokens is hedged in place, so the
    engine's retry re-judges a clean draft instead of the same failure."""
    from automedia.gates.fact_check import G0FactCheck
    from automedia.gates.llm_helpers import G0RewriteResult
    from tests.mock_llm import mock_llm_response

    failing = (
        "# 三步框架，让你周报满分\n\n很多人写周报没章法。\n\n"
        "写完记得对照检查一遍，让周报从此不再难！"
    )
    rewrite = G0RewriteResult(
        rewritten_content="# 三步写周报，一定轻松\n\n很多人写周报没章法。\n\n照着做一遍。",
        notes=["still absolute"],
    )
    ctx = {
        "content": failing,
        "topic": "新手写工作周报的三步框架",
        "source_data": None,
        "config": {"enable_llm": True},
    }
    with mock_llm_response(rewrite):
        result = G0FactCheck().execute(ctx)

    assert result["passed"] is False  # the gate still reports the original failure
    rewritten = result["modified_content"]
    assert "一定" not in rewritten and "轻松" not in rewritten
    assert hook_area_violations(rewritten) == []
