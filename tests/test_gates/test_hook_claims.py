"""HOOK CLAIMS single-source criteria (#520 phase 2).

Covers:

- ``prompts/hook_claims.py`` — the ONE copy of the ban list, the hook-area
  scan, and the deterministic G0 criteria (pure guarantee rejected, hedged
  checkable statements accepted).
- Template wiring — every HOOK CLAIMS template (3 generic + 20 platform
  variants) renders the shared list and none embeds a hand-copied full list.
- The deterministic criteria inside the G0 plausibility path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from automedia.prompts import load_prompt
from automedia.prompts.hook_claims import (
    HOOK_CLAIMS_BANNED_TOKENS,
    hook_area_violations,
    prompt_vars,
    render_banned_tokens,
)

# ---------------------------------------------------------------------------
# The ban list itself
# ---------------------------------------------------------------------------


def test_ban_list_matches_the_522_wording() -> None:
    """The 27 tokens #522 shipped, in order — nothing silently dropped."""
    expected = (
        "搞定",
        "学会",
        "包会",
        "速成",
        "保证",
        "决定",
        "必然",
        "一定",
        "满分",
        "精通",
        "逆袭",
        "躺赢",
        "必看",
        "必学",
        "错过就完了",
        "改变命运",
        "化繁为简",
        "轻松搞定",
        "不再难",
        "从此不再",
        "再也不",
        "告别",
        "摆脱",
        "零基础也能",
        "一招",
        "教你",
        "轻松",
    )
    assert expected == HOOK_CLAIMS_BANNED_TOKENS


def test_prompt_vars_render_the_shared_list() -> None:
    vars_ = prompt_vars()
    assert vars_["hook_claims_banned_tokens"] == render_banned_tokens()
    for token in HOOK_CLAIMS_BANNED_TOKENS:
        assert token in vars_["hook_claims_banned_tokens"]
    # Both language twins of the pattern description exist.
    assert vars_["hook_claims_patterns"] and vars_["hook_claims_patterns_zh"]


# ---------------------------------------------------------------------------
# hook_area_violations — the deterministic criteria
# ---------------------------------------------------------------------------


GUARANTEE_CONTENT = """# 三步框架，让你周报满分

很多人写周报没章法。三步框架能帮你把周报写清楚。

## 第二步：挑重点

把本周最有价值的三件事挑出来。

写完记得对照检查一遍，让周报从此不再难！
"""


def test_pure_guarantee_hooks_are_rejected() -> None:
    hits = hook_area_violations(GUARANTEE_CONTENT)
    tokens = {h.token for h in hits}
    assert "满分" in tokens  # H1 title
    assert "从此不再" in tokens  # closing CTA
    areas = {h.area for h in hits}
    assert "H1 title" in areas
    assert "CTA / closing paragraph" in areas


def test_body_text_is_not_scanned() -> None:
    """Outside the hook areas the ban list does not apply."""
    content = (
        "# 写周报的三个卡点\n\n第一段讲常见误区。\n\n中间引用团队的话，"
        "比如有人把周报叫「保证质量的仪式」。\n\n最后一行没有违禁词。"
    )
    assert hook_area_violations(content) == []


def test_hedged_rewrites_produce_no_hits() -> None:
    """The approved shapes — hedged, checkable, verifiable — are accepted."""
    hedged_contents = [
        "# 短视频劝退观众，往往就在前3秒\n\n很多人最开始的三秒就输掉了。"
        "\n\n欢迎对照你自己的视频检查一遍。",
        "# 写周报，大多数人第一步就卡住了\n\n第一步不是写，"
        "是先想清楚这周做成了什么。\n\n下次动笔前先列这三问。",
        "# 三步走下来，周报会顺很多\n\n框架不复杂，难在坚持。\n\n照着走一遍试试。",
        "# 新手周报，上手会比想象中顺\n\n别怕写得糙，先写起来。\n\n卡住了就回到第一步。",
    ]
    for content in hedged_contents:
        assert hook_area_violations(content) == [], content


def test_section_headings_and_first_paragraph_are_scanned() -> None:
    content = (
        "# 正常标题\n\n第一段有「教你」这个词。\n\n## 中间\n\n"
        "## 一招搞定结尾\n\n正文。\n\n结尾正常。"
    )
    hits = hook_area_violations(content)
    assert {(h.token, h.area) for h in hits} == {
        ("教你", "first paragraph"),
        ("一招", "section heading"),
        ("搞定", "section heading"),
    }


def test_script_format_without_headings_still_scanned() -> None:
    """Douyin-style scripts have no H1: opening line and closing CTA are the
    hook areas."""
    content = "开头3秒，决定你的短视频命运！\n\n中间正常口播。\n\n关注我，轻松学会剪辑！"
    hits = hook_area_violations(content)
    tokens = {h.token for h in hits}
    assert {"决定", "轻松", "学会"} <= tokens
    areas = {h.area for h in hits}
    assert areas == {"first paragraph", "CTA / closing paragraph"}


def test_empty_content_has_no_violations() -> None:
    assert hook_area_violations("") == []


def test_duplicate_token_reported_once_per_area() -> None:
    content = "# 决定命运的决定性一步\n\n正文。\n\n结尾决定。"
    hits = hook_area_violations(content)
    h1_hits = [h for h in hits if h.area == "H1 title"]
    assert len(h1_hits) == 1 and h1_hits[0].token == "决定"


def test_table_script_mid_rows_are_not_hook_areas() -> None:
    """Table-formatted scripts (douyin drafts): rows between the metadata
    header and the closing row are body — a visual-effect label like
    「职场逆袭」特效字 in the climax row must NOT deterministically fail the
    gate (the judge owns body claims)."""
    content = (
        "**主题：** 为什么你的周报领导总是跳过不读\n"
        "**品牌：** default\n"
        "**时长：** 45秒\n\n"
        "| 时间 | 画面内容 | 音效 | 口播文案 |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| **0:00-0:03** | **[黄金开头]**<br>文字贴纸：**领导跳过？** | "
        "**口播：**<br>为什么你的周报总被领导直接划走？ |\n"
        "| **0:45-0:55** | **[高潮/反转]**<br>背景出现“职场逆袭”特效字 | "
        "**口播：**<br>改完这篇，下周汇报直接C位出道。 |\n"
        "| **0:55-0:60** | **[引导互动]**<br>屏幕出现文字：**关注我** | "
        "**口播：**<br>想要万能周报模板？评论区扣“1”，我私发你。 |"
    )
    assert hook_area_violations(content) == []


def test_table_script_cta_row_is_still_scanned() -> None:
    """A banned token in the closing row's spoken line still fails."""
    content = (
        "| 时间 | 口播文案 |\n"
        "| :--- | :--- |\n"
        "| 0:00-0:03 | 为什么你的周报总被领导直接划走？ |\n"
        "| 0:55-0:60 | 三步搞定，学会投稿赚钱！ |"
    )
    hits = hook_area_violations(content)
    tokens = {h.token for h in hits}
    assert {"搞定", "学会"} <= tokens
    assert {h.area for h in hits} == {"CTA / closing paragraph"}


# ---------------------------------------------------------------------------
# Template wiring — no template carries its own copy of the list
# ---------------------------------------------------------------------------

_GENERIC_HOOK_CLAIMS_TEMPLATES = (
    "content_writer",
    "fact_check_g0_plausibility",
    "fact_check_g0_rewrite",
)

_PLATFORMS_DIR = Path(__file__).parents[2] / "src" / "automedia" / "prompts" / "platforms"


@pytest.mark.parametrize("template", _GENERIC_HOOK_CLAIMS_TEMPLATES)
def test_templates_render_the_shared_ban_list(template: str) -> None:
    rendered = load_prompt(template)
    assert render_banned_tokens() in rendered
    assert "{{ hook_claims" not in rendered  # variables resolved, not raw


@pytest.mark.parametrize("template", _GENERIC_HOOK_CLAIMS_TEMPLATES)
def test_generic_templates_use_the_render_variable(template: str) -> None:
    raw = (
        Path(__file__).parents[2] / "src" / "automedia" / "prompts" / f"{template}.j2"
    ).read_text(encoding="utf-8")
    assert "{{ hook_claims_banned_tokens }}" in raw
    # No hand-copied full list — the one copy lives in hook_claims.py.
    assert render_banned_tokens() not in raw


def test_all_platform_variants_render_the_shared_ban_list() -> None:
    """The 20 platform variants were ported like the SOURCED NUMBERS section:
    each carries the discipline and renders the shared list."""
    variant_paths = sorted(_PLATFORMS_DIR.glob("*/content_writer.j2"))
    assert len(variant_paths) == 20
    for path in variant_paths:
        raw = path.read_text(encoding="utf-8")
        assert "HOOK CLAIMS" in raw, f"{path} missing the discipline section"
        assert "{{ hook_claims_banned_tokens }}" in raw, f"{path} not rendering the shared list"
        assert render_banned_tokens() not in raw, f"{path} hand-copies the full ban list"
        rendered = load_prompt("content_writer", platform=path.parent.name)
        assert render_banned_tokens() in rendered


def test_user_override_receives_the_shared_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user override that uses the variables gets the shared list; one that
    ignores them renders unchanged."""
    from automedia import prompts as prompts_module

    override_dir = tmp_path / "overrides-prompts"
    override_dir.mkdir()
    (override_dir / "content_writer.j2").write_text(
        "banned: {{ hook_claims_banned_tokens }}", encoding="utf-8"
    )
    (override_dir / "fact_check_g0_plausibility.j2").write_text("plain override", encoding="utf-8")
    monkeypatch.setattr(prompts_module, "_OVERRIDE_DIR", override_dir)
    rendered = load_prompt("content_writer")
    assert rendered == f"banned: {render_banned_tokens()}"
    assert load_prompt("fact_check_g0_plausibility") == "plain override"


# ---------------------------------------------------------------------------
# Deterministic criteria in the G0 plausibility path
# ---------------------------------------------------------------------------


def _plausibility_context(content: str) -> dict[str, Any]:
    return {
        "content": content,
        "topic": "新手写工作周报的三步框架",
        "source_data": None,
        "config": {"enable_llm": True},
    }


def test_plausibility_rejects_guarantee_hooks_without_judge() -> None:
    """A pure guarantee-style hook fails deterministically — the judge never
    sees it; the one-shot rewrite IS attempted so the engine's retry can
    re-judge fixed text instead of re-judging the same failure."""
    from automedia.gates.fact_check import G0FactCheck
    from automedia.gates.llm_helpers import G0RewriteResult
    from tests.mock_llm import mock_llm_response

    rewrite = G0RewriteResult(
        rewritten_content=(
            "# 三步走下来，周报会顺很多\n\n很多人写周报没章法。\n\n写完记得对照检查一遍。"
        ),
        notes=["hedged the CTA"],
    )
    ctx = _plausibility_context(GUARANTEE_CONTENT)
    with mock_llm_response(rewrite) as mock_call:
        result = G0FactCheck().execute(ctx)
    assert mock_call.call_count == 1  # only the rewrite — no judge round-trip
    assert result["gate"] == "G0"
    assert result["passed"] is False
    assert result["method"] == "deterministic"
    check = result["checks"][0]
    assert check["name"] == "plausibility_check"
    assert "outcome-promise token(s) in hook area" in check["detail"]
    assert "满分" in check["detail"]
    assert result["error"]
    assert result["modified_content"].startswith("# 三步走下来")


def test_plausibility_rewrite_attempted_once_per_run() -> None:
    """The rewrite flag is set before the call — a failed rewrite can never
    produce a second attempt."""
    from automedia.gates.fact_check import G0FactCheck
    from automedia.gates.llm_helpers import G0RewriteResult
    from tests.mock_llm import mock_llm_response

    rewrite = G0RewriteResult(rewritten_content="改写后的内容", notes=[])
    ctx = _plausibility_context(GUARANTEE_CONTENT)
    with mock_llm_response(rewrite) as mock_call:
        G0FactCheck().execute(ctx)
        assert ctx["_g0_rewrite_attempted"] is True
    assert mock_call.call_count == 1


def test_plausibility_passes_hedged_content_to_the_judge() -> None:
    """A hedged, checkable hook reaches the LLM judge (no deterministic hit)."""
    from automedia.gates.fact_check import G0FactCheck
    from automedia.gates.llm_helpers import G0CheckResult
    from tests.mock_llm import mock_llm_response

    data = G0CheckResult(passed=True, issues=[], confidence=0.95)
    ctx = _plausibility_context(
        "# 三步走下来，周报会顺很多\n\n大多数人第一步就卡住。\n\n照着走一遍试试。"
    )
    with mock_llm_response(data):
        result = G0FactCheck().execute(ctx)
    assert result["gate"] == "G0"
    assert result["passed"] is True
    assert result["method"] == "llm"
    assert result["checks"][0]["name"] == "plausibility_check"


def test_plausibility_llm_failure_still_falls_back_to_skipped() -> None:
    """No violation + LLM failure → the pre-existing skipped contract holds."""
    from automedia.gates.fact_check import G0FactCheck
    from tests.mock_llm import mock_llm_failure

    ctx = _plausibility_context("任何没有违禁词的内容。")
    with mock_llm_failure():
        result = G0FactCheck().execute(ctx)
    assert result["passed"] is True
    assert result["status"] == "skipped"
