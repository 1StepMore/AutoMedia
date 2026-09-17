"""``GateContext.was_written`` 与 ``missing_input_result`` 判据的锁定测试。

中文说明：``GateContext.__contains__`` 对**任何已声明 dataclass 字段**恒返回
``True``（字段都有声明默认值），因此 ``any(key in ctx ...)`` 无法回答"这个键
到底有没有被上游产出过"。此前 ``missing_input_result`` 正是用了 ``in``，导致
V 门在真实运行路径上永不跳过（条件化是死代码）。本文件锁定修复后的双向语义：

* ``was_written`` 只认 ``ctx[key] = value`` 这条显式赋值路径；
* ``__contains__`` 的既有语义**未被改动**（仍恒 ``True``）；
* 登记表不污染 ``keys()`` / ``to_dict()`` 等 dict 兼容输出。
"""

from __future__ import annotations

from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import missing_input_result


class TestWasWritten:
    """``was_written`` 的语义边界。"""

    def test_false_for_declared_field_never_written(self) -> None:
        """已声明但从未赋值的字段 → ``was_written`` 为假（而 ``in`` 为真）。"""
        ctx = GateContext(topic="t")
        assert ctx.was_written("audio_path") is False
        # 锁定既有语义未变：``in`` 依旧恒 True，这正是不能用它的原因。
        assert "audio_path" in ctx

    def test_true_after_explicit_write(self) -> None:
        """``ctx[key] = value`` 之后 → ``was_written`` 为真。"""
        ctx = GateContext(topic="t")
        ctx["audio_path"] = "audio.mp3"
        assert ctx.was_written("audio_path") is True

    def test_falsy_values_still_count_as_written(self) -> None:
        """写出空值（``0`` / ``""`` / ``[]``）同样算"产出过"。

        这是刻意设计：全黑帧的 ``avg_brightness=0`` 不应被误判为"未产出"。
        """
        ctx = GateContext(topic="t")
        ctx["avg_brightness"] = 0
        ctx["transcription"] = ""
        ctx["entries"] = []
        assert ctx.was_written("avg_brightness") is True
        assert ctx.was_written("transcription") is True
        assert ctx.was_written("entries") is True

    def test_constructor_argument_does_not_register(self) -> None:
        """构造参数不算"显式写入"（约定：生产者必须用下标赋值）。"""
        ctx = GateContext(topic="t", brand="b", project_id="p", project_dir="d")
        assert ctx.was_written("topic") is False
        assert ctx.was_written("brand") is False

    def test_alias_resolution(self) -> None:
        """别名键与目标字段共享登记状态（``_gate_name`` → ``gate_name``）。"""
        ctx = GateContext(topic="t")
        ctx["_gate_name"] = "V1"
        assert ctx.was_written("gate_name") is True
        assert ctx.was_written("_gate_name") is True

    def test_non_field_key_written(self) -> None:
        """非字段键（extra）同样可登记，且不进入字段集合。"""
        ctx = GateContext(topic="t")
        ctx["video_path"] = "video.mp4"
        assert ctx.was_written("video_path") is True


class TestRegistryDoesNotLeak:
    """登记表不得污染 dict 兼容输出（hooks 会序列化 ``to_dict()``）。"""

    def test_keys_excludes_registry(self) -> None:
        ctx = GateContext(topic="t")
        ctx["audio_path"] = "audio.mp3"
        # 刻意检查 ``keys()`` 的输出（序列化面），而不是 ``in`` 的成员语义。
        assert "_written_keys" not in ctx.keys()  # noqa: SIM118

    def test_to_dict_excludes_registry(self) -> None:
        ctx = GateContext(topic="t")
        ctx["audio_path"] = "audio.mp3"
        payload: dict[str, Any] = ctx.to_dict()
        assert "_written_keys" not in payload
        assert payload["audio_path"] == "audio.mp3"


class TestMissingInputResultWithGateContext:
    """真实 ``GateContext`` 路径：判据从"恒不跳过"变为"按显式写入跳过"。"""

    def test_skipped_when_nothing_written(self) -> None:
        """全部必需键都没被写出 → 跳过（修复前这里恒为 ``None``）。"""
        ctx = GateContext(topic="t")
        result = missing_input_result("V2", ctx, ("transcription", "audio_path"))
        assert result is not None
        assert result["status"] == "skipped"
        assert result["passed"] is True
        assert "transcription/audio_path" in result["reason"]

    def test_not_skipped_when_any_key_written(self) -> None:
        """任一必需键写出过 → 不跳过，交由真实判定（残缺输入该失败而非静默跳过）。"""
        ctx = GateContext(topic="t")
        ctx["audio_path"] = "audio.mp3"
        assert missing_input_result("V2", ctx, ("transcription", "audio_path")) is None

    def test_not_skipped_when_all_keys_written(self) -> None:
        """全部写出 → 不跳过。"""
        ctx = GateContext(topic="t")
        ctx["audio_path"] = "audio.mp3"
        ctx["transcription"] = "hello world"
        assert missing_input_result("V2", ctx, ("transcription", "audio_path")) is None


class TestMissingInputResultWithPlainDict:
    """普通 dict 路径：语义与修复前完全一致（测试里大量使用）。"""

    def test_skipped_when_all_absent(self) -> None:
        result = missing_input_result("V5", {}, ("whisper_text", "srt_text"))
        assert result is not None
        assert result["status"] == "skipped"

    def test_not_skipped_when_any_present(self) -> None:
        assert missing_input_result("V5", {"srt_text": ""}, ("whisper_text", "srt_text")) is None
