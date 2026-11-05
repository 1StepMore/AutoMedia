"""Vision-entries producer — per-scene frames for the V1 gate (issue #387).

中文说明：#377 的第三点要求「出片后加一道画面与选题相关性检查（先用 V1）」，
但仓库里此前没有可信的 ``entries`` 生产者，V1 恒 ``skipped``。本模块补上
生产者：

1. **抽帧**：按 ``video_timeline_scenes`` 的切点，从成片里抽每场的中间帧与
   末帧（ffmpeg ``-ss <t> -frames:v 1``），落 ``03_video/frames/``；
2. **裁决**：
   - 文字面板来源（``scene_media_kinds[i] == "panel"``）**短路**：面板画的
     就是该场文案，相关性由构造保证——登记为已检且通过，无需模型；
   - 其余来源（生成图/复用图）需要视觉模型才能判相关性；仓库当前没有
     具备图像输入的 LLM 客户端，因此**如实记为未判定**（``checked=False``、
     ``verdict`` 写明原因），绝不默认 pass（issue #387 的红线）；
3. **接线**：runner 把 ``entries`` 写进 gate_context，V1 由此从 ``skipped``
     变成真实判定（全部场景可判时）；无可判定场景时 V1 继续 skip 并记账。

帧提取失败不抛错——该场帧路径留空并在 stats 里记账；但 ffmpeg 本体缺失
时直接抛错（此时整条视觉证据链都不存在，交给调用方降级为不写 entries）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from structlog import get_logger

log = get_logger(__name__)

#: injection seam for tests — signature: (argv list) -> CompletedProcess-like
Runner = Callable[..., subprocess.CompletedProcess[bytes]]

# 落盘 JPEG 质量（ffmpeg -q:v 2 ≈ 视觉上无损；PNG 对抽帧太大且更慢）。
_FFMPEG_FRAME_ARGS = ["-frames:v", "1", "-q:v", "2", "-y"]
_SUBPROCESS_TIMEOUT_S = 60


def _probe_duration(ffprobe_path: str, video_path: str, run: Runner) -> float | None:
    """成片时长（秒）；ffprobe 不可用/失败返回 None，调用方用保守余量。"""
    try:
        proc = run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                video_path,
            ]
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.decode(errors="replace").strip() or "")
    except ValueError:
        return None


def _extract_frame(
    ffmpeg_path: str,
    video_path: str,
    at_seconds: float,
    dest: str,
    run: Runner,
) -> str:
    """抽一帧；成功返回 ``dest``，失败返回空串（调用方记账，不外抛）。"""
    try:
        proc = run(
            [ffmpeg_path, "-ss", f"{max(at_seconds, 0.0):.3f}", "-i", video_path,
             *_FFMPEG_FRAME_ARGS, dest],
        )
    except OSError as exc:
        log.warning("vision_entries.ffmpeg_spawn_failed", dest=dest, error=str(exc))
        return ""
    if proc.returncode != 0 or not os.path.isfile(dest):
        log.warning(
            "vision_entries.frame_extract_failed",
            dest=dest,
            at=round(at_seconds, 3),
            stderr=str(proc.stderr[-200:] if proc.stderr else ""),
        )
        return ""
    return dest


def build_vision_entries(
    video_path: str,
    scenes: list[dict[str, Any]],
    scene_media: list[str],
    scene_media_kinds: list[str],
    frames_dir: str,
    *,
    ffmpeg_path: str | None = None,
    ffprobe_path: str | None = None,
    run: Runner | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """从成片按场景切点抽帧并给出逐场 ``entries``（V1 的输入）。

    Args:
        video_path: 成片路径（``03_video/output.mp4``）。
        scenes: ``video_timeline_scenes``（id/index/start/duration/text）。
        scene_media: 每场素材路径（可与 ``scenes`` 不等长，缺的场记 ``missing``）。
        scene_media_kinds: 每场素材来源（``panel``/``generated``/``reused``），
            与 ``scene_media`` 对齐；缺的场视作 ``missing``。
        frames_dir: 帧落盘目录（``03_video/frames/``），不存在则创建。
        ffmpeg_path/ffprobe_path/run: 测试注入位；缺省用 PATH 探测与真跑。

    Returns:
        ``(entries, stats)``。``entries`` 逐场含 ``mid_frame_path``、
        ``end_silence_frame_path``、``checked``、``qa_passed``、``verdict``；
        ``stats`` 记 ``frames_extracted`` / ``frames_failed`` / ``judged`` /
        ``unjudged``。

    Raises:
        FileNotFoundError: ffmpeg 不可用（无帧可抽，调用方降级为不写 entries）。
    """
    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not resolved_ffmpeg:
        raise FileNotFoundError("ffmpeg not found on PATH — no frames can be extracted")
    resolved_ffprobe = ffprobe_path or shutil.which("ffprobe")
    runner: Runner = run or subprocess.run  # type: ignore[assignment]

    os.makedirs(frames_dir, exist_ok=True)
    duration = None
    if resolved_ffprobe:
        duration = _probe_duration(resolved_ffprobe, video_path, runner)

    entries: list[dict[str, Any]] = []
    stats = {"frames_extracted": 0, "frames_failed": 0, "judged": 0, "unjudged": 0}
    # ffprobe 缺席时给末帧留保守余量，避免 -ss 越过 EOF 抽到空。
    end_margin = 0.05 if duration is not None else 0.25

    for i, scene in enumerate(scenes):
        start = float(scene.get("start", 0.0) or 0.0)
        length = float(scene.get("duration", 0.0) or 0.0)
        scene_no = str(scene.get("id", i + 1))
        mid_path = os.path.join(frames_dir, f"scene-{scene_no}-mid.jpg")
        end_path = os.path.join(frames_dir, f"scene-{scene_no}-end.jpg")

        mid = _extract_frame(resolved_ffmpeg, video_path, start + length / 2, mid_path, runner)
        end_at = start + length - end_margin if duration is None else min(
            start + length, duration - end_margin
        )
        end = _extract_frame(resolved_ffmpeg, video_path, end_at, end_path, runner)
        stats["frames_extracted"] += int(bool(mid)) + int(bool(end))
        stats["frames_failed"] += int(not mid) + int(not end)

        kind = scene_media_kinds[i] if i < len(scene_media_kinds) else "missing"
        if not mid and not end:
            # 两帧都抽失败：该场没有视觉证据，谈不上判定——记 unjudged 并写明
            # 原因；若**所有**场次都如此，下面会整体 raise（不写 entries）。
            checked, qa_passed = False, False
            verdict = "unjudged: frame extraction failed — no visual evidence"
            stats["unjudged"] += 1
        elif kind == "panel":
            # 文字面板：面板文字就是该场文案，相关性由构造保证——只登记。
            checked, qa_passed, verdict = True, True, (
                "panel (by construction: the panel text is this scene's copy)"
            )
            stats["judged"] += 1
        else:
            # 生成图/复用图：需要视觉模型判相关性；仓库当前没有图像输入的
            # LLM 客户端，如实记未判定，绝不默认 pass（#387）。
            checked, qa_passed, verdict = False, False, (
                "unjudged: no vision-capable model configured — frame extracted "
                "for future VLM judging"
            )
            stats["unjudged"] += 1

        entries.append(
            {
                "scene_id": scene_no,
                "scene_index": i,
                "scene_text": str(scene.get("text", "") or ""),
                "mid_frame_path": mid,
                "end_silence_frame_path": end,
                "source": kind,
                "checked": checked,
                "qa_passed": qa_passed,
                "verdict": verdict,
            }
        )

    if scenes and stats["frames_extracted"] == 0:
        # 视觉证据链整链为空（ffmpeg 坏/视频不可读）：不写 entries，让 V1
        # 如实 skip——拿着全空的帧路径去判只会产出关于空值的失败（#387）。
        raise RuntimeError(
            "no frames could be extracted from the rendered video — "
            "the visual evidence chain is empty"
        )

    log.info(
        "vision_entries.built",
        scenes=len(entries),
        **stats,
    )
    return entries, stats
