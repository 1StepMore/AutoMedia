"""Structured spoken-line extraction for SRT cues (#654).

The storyboard draft mixes spoken lines with stage directions that live
*outside* any bracket (``[切] 创作者对镜说话，语速快``).  Word-level cleaning
(#390/#455/#459) only strips the bracket itself, so the direction text leaked
into ``04_audio/narration.srt``.  These tests pin the structural fix: only
lines labelled ``口播：`` / ``旁白：`` are narration; everything else is
dropped, and the V5 residue check fails the gate when a stage direction still
reaches a cue.

The draft fragment below is the real #654 draft, reduced to the lines around
the two defects (synthetic — no production data).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from automedia.gates.mp3_vs_srt import V5Mp3VsSrt
from automedia.pipelines.audio_pipeline import AudioPipeline, extract_spoken_lines

DRAFT = """\
**0:00-0:03 黄金开头**
- **口播**：你发现没？现在扎进播客的品牌一抓一大把，但真做起来的，真没几个。
- **[画面：文字贴纸]**「播客≠硬广！」+ 快切手机播客页面
- **[音效：卡点重音]**

**0:03-0:45 正文**
- **[切]** 创作者对镜说话，语速快
- **口播**：你懂吧，播客这玩意儿，核心就靠声音。
"""

#: Same regex as ``automedia.gates.mp3_vs_srt._STAGE_MARKER_RE`` — duplicated
#: here on purpose so this test keeps biting even if the gate's copy drifts.
_STAGE_MARKER_RE = re.compile(
    r"\[(?:画面|音效|转场|切|镜头|特写|字幕|花字|旁白|视觉|bgm|sfx)\s*[:：\]]"
    r"|口播\s*[:：]|镜头|语速|贴纸|快切|特写|推近|空镜",
    re.IGNORECASE,
)


class TestExtractSpokenLines:
    def test_stage_direction_after_cut_marker_excluded(self) -> None:
        """``[切]`` 后面跟的说明文字不是口播——这正是 #654 的 bug 形态。"""
        joined = "\n".join(extract_spoken_lines(DRAFT))
        assert "快切手机播客页面" not in joined
        assert "创作者对镜说话" not in joined
        assert "语速快" not in joined
        assert "你发现没" in joined  # 口播本体还在

    def test_quoted_slogan_without_spoken_label_excluded(self) -> None:
        """只有画面标签的行整行丢弃——引号里的口号没被念出来。"""
        joined = "".join(extract_spoken_lines(DRAFT))
        assert "播客≠硬广" not in joined

    def test_spoken_lines_preserved_in_order(self) -> None:
        """标签后的文本按原顺序完整保留，不吞字。"""
        assert extract_spoken_lines(DRAFT) == [
            "你发现没？现在扎进播客的品牌一抓一大把，但真做起来的，真没几个。",
            "你懂吧，播客这玩意儿，核心就靠声音。",
        ]

    def test_multiple_labels_on_one_line_all_collected_in_order(self) -> None:
        assert extract_spoken_lines("口播：先跑通。口播：再谈产量。") == [
            "先跑通。",
            "再谈产量。",
        ]

    def test_freeform_script_without_labels_falls_back(self) -> None:
        """没有口播标签的自由格式稿件退回清洗路径，字幕照常产出。"""
        freeform = "## 标题\n\n[画面：叹气]三个人管六个账号。\n- 第二句。"
        assert extract_spoken_lines(freeform) == ["三个人管六个账号。", "第二句。"]
        cues = AudioPipeline().split_caption_cues(freeform)
        assert "".join(cues) == "三个人管六个账号。第二句。"


class TestSrtEndToEnd:
    def test_srt_has_no_stage_markers(self, tmp_path: Path) -> None:
        """端到端：真实 draft 片段生成的 SRT 不含任何舞台指示。"""
        path = AudioPipeline().generate_srt_from_script(
            DRAFT, 30.0, str(tmp_path / "narration.srt")
        )
        assert path
        body = Path(path).read_text(encoding="utf-8")
        assert body.strip()
        assert not _STAGE_MARKER_RE.search(body)
        assert "你发现没" in body
        assert "快切" not in body


class TestGateStageMarkerAssertion:
    def test_gate_rejects_stage_marker_in_srt(self) -> None:
        """命中舞台指示正则的 cue 必须把 V5 判红，并写明 cue 序号与片段。"""
        srt = (
            "1\n00:00:00,000 --> 00:00:02,000\n「播客≠硬广！」+ 快切手机播客页面\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\n你懂吧，播客这玩意儿，核心就靠声音。\n"
        )
        ctx: dict[str, Any] = {
            "whisper_text": "你懂吧播客这玩意儿核心就靠声音",
            "srt_text": srt,
        }
        result = V5Mp3VsSrt().execute(ctx)
        assert result["passed"] is False
        residue = next(c for c in result["checks"] if c["name"] == "structure_label_residue")
        assert residue["passed"] is False
        assert "cue 1 混入舞台指示：快切" in residue["detail"]

    def test_clean_srt_does_not_trip_the_stage_marker_check(self) -> None:
        """干净字幕不误伤：普通叙述里的日常用词不能把 V5 判红。"""
        ctx: dict[str, Any] = {
            "whisper_text": "先把流程跑通再谈产量",
            "srt_text": "1\n00:00:00,000 --> 00:00:04,000\n先把流程跑通，再谈产量。\n",
        }
        result = V5Mp3VsSrt().execute(ctx)
        residue = next(c for c in result["checks"] if c["name"] == "structure_label_residue")
        assert residue["passed"] is True
