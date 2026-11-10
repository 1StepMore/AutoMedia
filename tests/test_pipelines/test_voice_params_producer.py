"""V4's honest voice-params producer (#472).

The edge-tts engine never returns the voice it used, so the adapter layer in
``AudioPipeline.generate_tts`` records the resolved parameters per synthesis
("调用参数即实际参数" — the documented assumption), and the runner media stage
writes V4's inputs: the actual ``voice_id``/``speaking_rate``/``segments``
plus the brand-asset ``expected_voice_id`` (same fallback chain as
``language_config.resolve_language_config`` — never hard-coded).
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from automedia.pipelines.audio_pipeline import AudioPipeline
from automedia.pipelines.runner import _expected_voice_from_brand


class TestAudioPipelineRecordsVoiceParams:
    def test_generate_tts_records_resolved_voice(self, tmp_path: Any) -> None:
        pipeline = AudioPipeline(config={})
        out = tmp_path / "narration.mp3"
        with (
            mock.patch("automedia.pipelines.audio_pipeline.resolve_engine_chain", return_value=[]),
            mock.patch("automedia.pipelines.audio_pipeline.subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            pipeline.generate_tts("你好世界", output_path=str(out))
        assert pipeline.last_voice_params == {
            "voice_id": "zh-CN-YunxiNeural",
            "rate": 0.0,
            "pitch": 0.0,
        }

    def test_explicit_voice_param_is_what_gets_recorded(self, tmp_path: Any) -> None:
        pipeline = AudioPipeline(config={})
        out = tmp_path / "narration.mp3"
        with (
            mock.patch("automedia.pipelines.audio_pipeline.resolve_engine_chain", return_value=[]),
            mock.patch("automedia.pipelines.audio_pipeline.subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            pipeline.generate_tts("你好", voice="zh-CN-YunyangNeural", output_path=str(out))
        assert pipeline.last_voice_params["voice_id"] == "zh-CN-YunyangNeural"


class TestExpectedVoiceFromBrand:
    def test_brand_language_voice_wins(self) -> None:
        brand = {"languages": {"zh": {"tts_voice": "zh-CN-XiaoxiaoNeural"}}}
        assert _expected_voice_from_brand(brand) == "zh-CN-XiaoxiaoNeural"

    def test_missing_languages_falls_back_to_shared_default(self) -> None:
        assert _expected_voice_from_brand({}) == "zh-CN-YunxiNeural"
        assert _expected_voice_from_brand(None) == "zh-CN-YunxiNeural"

    def test_blank_voice_falls_back(self) -> None:
        brand = {"languages": {"zh": {"tts_voice": "  "}}}
        assert _expected_voice_from_brand(brand) == "zh-CN-YunxiNeural"


class TestV4InputsWrittenByRunner:
    """链路级：TTS 产物落盘 ⇒ V4 输入齐备；无 TTS ⇒ 不写（诚实 skip）."""

    def test_inputs_written_after_tts(self, tmp_path: Any) -> None:
        # 链路级行为由 tests/test_media_production.py 的全链路替身覆盖；
        # 这里钉 V4 输入键的形状契约。
        from automedia.gates._result import missing_input_result

        ctx: dict[str, Any] = {
            "voice_id": "zh-CN-YunxiNeural",
            "speaking_rate": 0.0,
            "expected_voice_id": "zh-CN-YunxiNeural",
            "segments": [
                {
                    "id": "scene-1",
                    "voice_params": {"voice_id": "zh-CN-YunxiNeural", "rate": 0.0, "pitch": 0.0},
                },
                {
                    "id": "scene-2",
                    "voice_params": {"voice_id": "zh-CN-YunxiNeural", "rate": 0.0, "pitch": 0.0},
                },
            ],
        }
        assert missing_input_result("V4", ctx, ("voice_id", "segments")) is None

    def test_missing_inputs_still_skip(self) -> None:
        from automedia.gates._result import missing_input_result

        assert missing_input_result("V4", {}, ("voice_id", "segments")) is not None
