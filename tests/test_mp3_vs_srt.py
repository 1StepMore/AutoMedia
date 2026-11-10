"""Tests for V5Mp3VsSrt gate — structural subtitle/audio agreement (#469).

The retired criterion was a whole-string character similarity (``>= 0.80``).
These tests pin the replacement (per-cue anchor coverage, cue order, uncovered
ASR speech, structure residue) and pin the retired value to an
observation-only field.  All fixtures are synthetic.
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates.base import BaseGate, _registry
from automedia.gates.mp3_vs_srt import (
    _CHECK_NAMES,
    _CUE_COVERAGE_MIN,
    V5Mp3VsSrt,
    _parse_srt_cues,
    _strip_srt_timestamps,
)

_SRT_SAMPLE = """\
1
00:00:01,000 --> 00:00:03,000
Hello world this is a test

2
00:00:03,500 --> 00:00:05,000
Of subtitle rendering
"""

_WHISPER_SAMPLE = "Hello world this is a test of subtitle rendering"

# Synthetic Chinese narration: three cues, transcribed with the kind of
# homophone noise real ASR produces (喂→为, 吐→土) -- still the same words.
_CJK_SRT = """\
1
00:00:00,000 --> 00:00:04,000
先把流程跑通，再谈产量。

2
00:00:04,000 --> 00:00:08,000
没有规矩，它就是大号噪音制造机。

3
00:00:08,000 --> 00:00:12,000
你喂进去垃圾，它吐出来的全是废品。
"""

_CJK_ASR = "先把流程跑通再谈产量。没有规矩他就是大号噪音制造机。你为进去垃圾他土出来的全是费品。"

_POLLUTED_BODY = "主题：企业用AI做内容 口播：先把链路跑顺。 [切] 镜头1｜0:03-0:09"

_POLLUTED_SRT = """\
1
00:00:00,000 --> 00:00:04,000
主题：企业用AI做内容 口播：先把链路跑顺。
"""


def _make_context(
    *,
    whisper_text: str = _WHISPER_SAMPLE,
    srt_text: str = _SRT_SAMPLE,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "whisper_text": whisper_text,
        "srt_text": srt_text,
    }
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _check(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in result["checks"] if c["name"] == name)


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "failed") -> dict[str, dict[str, Any]]:
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


class TestV5Metadata:
    def test_gate_name(self) -> None:
        assert V5Mp3VsSrt().gate_name == "V5"

    def test_failure_mode_is_rewrite(self) -> None:
        assert V5Mp3VsSrt().failure_mode == "retry"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V5Mp3VsSrt, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V5" in _registry
        assert _registry.get("V5") is V5Mp3VsSrt

    def test_check_names_are_unique_and_cover_all_criteria(self) -> None:
        assert len(_CHECK_NAMES) == len(set(_CHECK_NAMES))
        assert set(_CHECK_NAMES) == {
            "cue_anchor_coverage",
            "cue_order_consistency",
            "uncovered_speech",
            "structure_label_residue",
            "srt_not_empty",
            "whisper_not_empty",
            "whisper_vs_srt_diff",
            "semantic_consistency",
        }


class TestV5MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V5"
        assert result["error"] is None
        assert len(result["checks"]) == len(_CHECK_NAMES)

    @pytest.mark.parametrize("name", _CHECK_NAMES)
    def test_each_check_can_fail_gate_alone(self, name: str) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_fail_check(name)))
        assert _check(result, name)["passed"] is False
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V5Mp3VsSrt().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV5CleanFilmPasses:
    def test_clean_english_pair_passes(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context())
        assert result["passed"] is True, [c for c in result["checks"] if not c["passed"]]

    def test_clean_cjk_pair_with_asr_homophones_passes(self) -> None:
        """Real ASR misspells characters; the same words must still pass."""
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=_CJK_ASR, srt_text=_CJK_SRT))
        assert result["passed"] is True, [c for c in result["checks"] if not c["passed"]]
        coverage = _check(result, "cue_anchor_coverage")
        assert "all 3 cues anchored" in coverage["detail"]

    def test_clean_pair_residue_check_passes(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context())
        assert _check(result, "structure_label_residue")["passed"] is True


class TestV5StructuralFailures:
    """The four failure forms of #469 must each fail the gate independently."""

    def test_block_swap_fails_order_alone(self) -> None:
        """整段错位:字幕顺序与音频顺序相反,文本本身都在。"""
        srt = """\
1
00:00:00,000 --> 00:00:04,000
第一节我们讲流程设计

2
00:00:04,000 --> 00:00:08,000
第二节我们讲产量提升
"""
        # Audio plays block 2 first, then block 1.
        whisper = "第二节我们讲产量提升第一节我们讲流程设计"
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=whisper, srt_text=srt))
        order = _check(result, "cue_order_consistency")
        coverage = _check(result, "cue_anchor_coverage")
        assert coverage["passed"] is True  # both blocks are anchored
        assert order["passed"] is False
        assert "inverted" in order["detail"]
        assert result["passed"] is False

    def test_missed_segment_fails_coverage_alone(self) -> None:
        """漏念一段:音频里没念第二条字幕。"""
        srt = """\
1
00:00:00,000 --> 00:00:04,000
先把流程跑通

2
00:00:04,000 --> 00:00:08,000
没有规矩它就是大号噪音制造机
"""
        whisper = "先把流程跑通"
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=whisper, srt_text=srt))
        coverage = _check(result, "cue_anchor_coverage")
        order = _check(result, "cue_order_consistency")
        uncovered = _check(result, "uncovered_speech")
        assert coverage["passed"] is False
        assert "cue #2" in coverage["detail"]
        assert order["passed"] is True  # one anchor only; order is not the defect
        assert uncovered["passed"] is True  # nothing extra was spoken
        assert result["passed"] is False

    def test_extra_segment_fails_uncovered_speech_alone(self) -> None:
        """多念一段:音频多说了字幕没有的一句话。"""
        srt = """\
1
00:00:00,000 --> 00:00:04,000
先把流程跑通
"""
        whisper = "先把流程跑通另外我们还提供免费咨询服务欢迎随时联系我们"
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=whisper, srt_text=srt))
        coverage = _check(result, "cue_anchor_coverage")
        uncovered = _check(result, "uncovered_speech")
        assert coverage["passed"] is True
        assert uncovered["passed"] is False
        assert "no subtitle coverage" in uncovered["detail"]
        assert result["passed"] is False

    def test_structure_residue_fails_alone(self) -> None:
        """结构残留:SRT 与音频都来自同一份脏文本,覆盖率再高也得红。"""
        result = V5Mp3VsSrt().execute(
            _make_context(whisper_text=_POLLUTED_BODY, srt_text=_POLLUTED_SRT)
        )
        residue = _check(result, "structure_label_residue")
        assert residue["passed"] is False
        assert "srt" in residue["detail"]
        assert result["passed"] is False

    def test_residue_detail_names_each_pattern(self) -> None:
        srt = """\
1
00:00:00,000 --> 00:00:09,000
主题：企业用AI做内容 口播：先把链路跑顺。 [切] 镜头1｜0:03-0:09
"""
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=_POLLUTED_BODY, srt_text=srt))
        residue = _check(result, "structure_label_residue")
        for label in (
            "metadata_label",
            "spoken_prefix",
            "transition_tag",
            "shot_label",
            "timecode",
        ):
            assert label in residue["detail"]
        assert "whisper" in residue["detail"] and "srt" in residue["detail"]

    @pytest.mark.parametrize(
        "fragment",
        [
            "主题：先跑通流程",  # metadata label
            "品牌：壹目贯维",  # metadata label
            "镜头2｜0:09-0:15",  # shot header + timecode
            "口播：先把链路跑顺。",  # spoken prefix
            "先把链路跑顺。[切]",  # transition tag
        ],
    )
    def test_each_pollution_category_fails_alone(self, fragment: str) -> None:
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=fragment, srt_text=_SRT_SAMPLE))
        residue = _check(result, "structure_label_residue")
        assert residue["passed"] is False, fragment
        assert result["passed"] is False

    def test_bare_shen_tou_without_digit_is_not_a_shot_label(self) -> None:
        """``镜头`` in ordinary prose (no digit, no timecode) is not scaffolding."""
        result = V5Mp3VsSrt().execute(
            _make_context(whisper_text="把镜头对准产品本身。", srt_text=_SRT_SAMPLE)
        )
        residue = _check(result, "structure_label_residue")
        assert residue["passed"] is True


class TestV5ObservationField:
    """#469: the retired similarity is reported but never drives the verdict."""

    def test_low_similarity_is_not_a_failure(self) -> None:
        """Same words, heavy ASR noise: similarity far below 80%, still green.

        This is exactly the clean-film case the old threshold rejected (#462).
        """
        noisy = "你为进去拉机他土出来的全是费品先把流程跑通再谈产量没有规矩它就是大号早音智早机"
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=noisy, srt_text=_CJK_SRT))
        diff = _check(result, "whisper_vs_srt_diff")
        assert diff["passed"] is True
        assert "observation only" in diff["detail"]
        assert "no longer a pass/fail criterion" in diff["detail"]

    def test_unrelated_text_fails_on_structure_not_on_similarity(self) -> None:
        """Text that shares nothing with the SRT fails the anchor check."""
        result = V5Mp3VsSrt().execute(
            _make_context(
                whisper_text="完全无关的另一段内容讲的是天气和交通",
                srt_text="1\n00:00:01,000 --> 00:00:02,000\nhello world test\n",
            )
        )
        diff = _check(result, "whisper_vs_srt_diff")
        coverage = _check(result, "cue_anchor_coverage")
        assert diff["passed"] is True  # observation field stays green
        assert "observation only" in diff["detail"]
        assert coverage["passed"] is False
        assert result["passed"] is False

    def test_observation_field_reported_within_receiver_report(self) -> None:
        """Check names the gate-report row keeps: name/passed/detail."""
        result = V5Mp3VsSrt().execute(_make_context())
        for check in result["checks"]:
            assert set(check) == {"name", "passed", "detail"}


class TestV5SemanticLayer:
    def test_semantic_layer_reports_honest_skip(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context())
        semantic = _check(result, "semantic_consistency")
        assert semantic["passed"] is True
        assert semantic["detail"] == "semantic: skipped(no key)"


class TestV5ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_missing_context_keys(self) -> None:
        """Absent inputs mean no audio/subtitle pair exists → the gate reports skipped.

        中文说明：健康度整改（P0-1）之后，缺失输入必须显式记为 ``skipped``，
        而不是对从未产出的一对音视频产物给出一个关于空值的 verdict。
        """
        result = V5Mp3VsSrt().execute({})
        assert result["gate"] == "V5"
        assert result["status"] == "skipped"
        assert result["passed"] is True
        assert "checks" not in result
        assert "whisper_text" in result["reason"]

    def test_empty_srt_fails(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(srt_text=""))
        assert _check(result, "srt_not_empty")["passed"] is False
        assert result["passed"] is False

    def test_empty_whisper_fails(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=""))
        assert _check(result, "whisper_not_empty")["passed"] is False
        assert result["passed"] is False

    def test_unparseable_srt_fails_instead_of_passing_vacuously(self) -> None:
        """Plain prose is not an SRT file — no cue can be verified, so fail."""
        result = V5Mp3VsSrt().execute(
            _make_context(whisper_text="一句普通的话", srt_text="一句普通的话，没有时间轴。")
        )
        coverage = _check(result, "cue_anchor_coverage")
        assert coverage["passed"] is False
        assert "no SRT cues parsed" in coverage["detail"]
        assert result["passed"] is False


class TestV5SrtParsing:
    def test_strip_srt_timestamps(self) -> None:
        cleaned = _strip_srt_timestamps(_SRT_SAMPLE)
        assert "00:00:01" not in cleaned
        assert "1" not in cleaned.strip() or "Hello" in cleaned
        assert "Hello" in cleaned

    def test_parse_cues_reads_timing_and_text(self) -> None:
        cues = _parse_srt_cues(_SRT_SAMPLE)
        assert [c.index for c in cues] == [1, 2]
        assert cues[0].start == "00:00:01,000"
        assert cues[0].end == "00:00:03,000"
        assert cues[0].text == "Hello world this is a test"

    def test_parse_cues_handles_crlf_and_missing_blank_lines(self) -> None:
        srt = (
            "1\r\n00:00:00,000 --> 00:00:02,000\r\n第一句\r\n"
            "2\r\n00:00:02,000 --> 00:00:04,000\r\n第二句\r\n"
        )
        cues = _parse_srt_cues(srt)
        assert [c.text for c in cues] == ["第一句", "第二句"]

    def test_parse_cues_strips_html_tags(self) -> None:
        srt = "1\n00:00:00,000 --> 00:00:02,000\n<i>斜体字幕</i>\n"
        assert _parse_srt_cues(srt)[0].text == "斜体字幕"

    def test_parse_cues_ignores_preamble(self) -> None:
        srt = "WEBVTT-ish preamble\n\n1\n00:00:00,000 --> 00:00:02,000\n正文\n"
        assert [c.text for c in _parse_srt_cues(srt)] == ["正文"]


class TestV5Thresholds:
    def test_coverage_threshold_is_calibrated_between_bad_and_clean(self) -> None:
        """Real reading: clean worst cue 0.53, unspoken cue 0.33 (#469)."""
        assert 0.33 < _CUE_COVERAGE_MIN < 0.53

    def test_failure_mode_is_retry_not_stop(self) -> None:
        assert V5Mp3VsSrt().failure_mode == "retry"
