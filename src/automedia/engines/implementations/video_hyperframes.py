"""HyperFrames video rendering engine with FFmpeg fallback.

Renders a video from the provided assets (images, audio, subtitles, template
directory, and content text) using either the ``hyperframes`` CLI tool or,
as a fallback, an ``ffmpeg`` slideshow pipeline.

Class
-----
HyperFramesVideoEngine
    Concrete :class:`~automedia.engines.base.BaseVideoEngine` subclass that
    auto-registers with ``engine_name="hyperframes"`` and ``modality="video"``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date
from typing import Any, ClassVar

import jinja2

from automedia.core.tool_paths import ToolPathError, find_tool
from automedia.engines.base import BaseVideoEngine
from automedia.engines.errors import EngineExecutionError

logger = logging.getLogger(__name__)


class HyperFramesVideoEngine(BaseVideoEngine):
    """Render a video from images, audio, and subtitles.

    **Primary path** — ``hyperframes`` CLI:

    1. Copy all assets into a temporary working directory.
    2. Invoke ``<cli...> render -q <quality> -o <output> <project_dir>``
       (project directory as positional argument, per ``hyperframes
       render --help`` — there is no ``--assets`` option).
    3. On success return ``output_path``.
    4. On failure: **degrade to the FFmpeg slideshow only when
       ``engines.video.hyperframes.allow_degrade`` is enabled**; otherwise
       re-raise so the pipeline reports the render failure instead of
       shipping a slideshow that looks like a finished video (#414).

    The CLI itself is resolved via :meth:`_resolve_cli_base` with the
    priority ``cli_command`` > ``cli_path`` > ``PATH`` lookup, so both
    a global install and a per-project npm install (``npx hyperframes``
    or ``node <abs>/dist/cli.js``) are supported.

    **Fallback path** — ``ffmpeg`` slideshow (only with ``allow_degrade``):

    1. Build a slideshow video from the image sequence.
    2. Mux the audio track onto the result.
    3. Write the final file to ``output_path``. The runner marks the
       artifact degraded (``render-meta.json`` sidecar + gate-report note).

    **When both tools are absent**, :meth:`check_available` returns
    ``(False, ...)``.  If the engine is used anyway, :meth:`render` raises
    :class:`EngineExecutionError`.
    """

    engine_name: ClassVar[str] = "hyperframes"
    modality: ClassVar[str] = "video"

    #: Whether the last :meth:`render` produced a video by falling back to the
    #: FFmpeg slideshow instead of HyperFrames (#383).  A slideshow is a still
    #: frame plus audio — technically playable, but never what the configured
    #: engine was asked to do, so callers must be able to say so out loud.
    last_render_degraded: bool = False

    #: Why the primary path failed, verbatim (command exit code + stderr tail).
    last_render_reason: str = ""

    #: Truthy strings accepted for the ``allow_degrade`` config key, which may
    #: arrive as a YAML bool or as a string via the generic
    #: ``AUTOMEDIA_ENGINES_VIDEO_HYPERFRAMES_ALLOW_DEGRADE`` env override.
    _TRUTHY = ("1", "true", "yes", "on")

    def _degrade_allowed(self) -> bool:
        """Whether a failed/missing hyperframes render may degrade to slideshow.

        Default is **False** (#414): a slideshow produced after a render
        failure looks like a finished video on disk, the pipeline stays
        ``success``, and the video track never gets gate evidence. Enabling
        ``engines.video.hyperframes.allow_degrade`` restores the pre-#414
        behaviour explicitly, with the output marked degraded by the runner.
        """
        raw = self._config.get("allow_degrade", False)
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in self._TRUTHY

    # ------------------------------------------------------------------
    # Constants for the FFmpeg fallback slideshow pipeline
    # ------------------------------------------------------------------

    _FALLBACK_FRAMERATE: float = 0.5
    """Input framerate (images per second) for the slideshow."""

    _OUTPUT_FRAMERATE: int = 30
    """Output video framerate after encoding."""

    _VIDEO_CODEC: str = "libx264"
    """Video codec used by the FFmpeg fallback."""

    _DEFAULT_SCENE_DURATION: int = 10
    """Default seconds per scene when audio duration cannot be detected."""

    # ------------------------------------------------------------------
    # Dependency check
    # ------------------------------------------------------------------

    def _resolve_cli_base(self) -> list[str] | None:
        """Resolve the ``hyperframes`` CLI invocation prefix.

        Priority: ``cli_command`` > ``cli_path`` > ``shutil.which(...)``.

        - ``cli_command``: explicit command array, e.g.
          ``["npx", "hyperframes"]`` or
          ``["node", "/abs/path/to/dist/cli.js"]`` (per-project npm install).
        - ``cli_path``: absolute path to an executable, e.g.
          ``/usr/local/bin/hyperframes`` or a ``dist/cli.js`` file
          (``.js`` files are invoked via ``node``).
        - Fallback: ``shutil.which("hyperframes")`` (global install on ``PATH``).

        Returns
        -------
        list[str] | None
            The CLI prefix (e.g. ``["hyperframes"]``), or ``None`` when no
            usable CLI was found.
        """
        cli_command: Any = self._config.get("cli_command")
        if cli_command:
            return [str(part) for part in cli_command]

        cli_path: Any = self._config.get("cli_path")
        if cli_path:
            cli_path_str: str = str(cli_path)
            if os.path.isfile(cli_path_str):
                if cli_path_str.endswith(".js"):
                    return ["node", cli_path_str]
                return [cli_path_str]
            logger.warning(
                "Configured hyperframes cli_path does not exist: %s; falling back to PATH lookup.",
                cli_path_str,
            )

        hyperframes_path: str | None = shutil.which("hyperframes")
        if hyperframes_path:
            return [hyperframes_path]
        return None

    def check_available(self) -> tuple[bool, str]:
        """Verify that at least one of ``hyperframes`` or ``ffmpeg`` is usable.

        The ``hyperframes`` CLI is resolved with the same logic as rendering:
        ``cli_command`` config > ``cli_path`` config > ``PATH`` lookup, so a
        per-project npm install (``npx hyperframes`` or ``node .../dist/cli.js``)
        counts as available even when no global ``hyperframes`` is on ``PATH``.

        Returns
        -------
        tuple[bool, str]
            ``(True, ...)`` if either tool is found; ``(False, ...)`` only
            when neither is available.
        """
        cli_base: list[str] | None = self._resolve_cli_base()
        if cli_base:
            return (True, f"hyperframes found: {' '.join(cli_base)}")

        try:
            ffmpeg_path: str | None = find_tool("ffmpeg")
        except ToolPathError as exc:
            return (False, str(exc))

        if ffmpeg_path:
            return (True, f"hyperframes not found; ffmpeg fallback at {ffmpeg_path}")

        return (
            False,
            "Neither 'hyperframes' nor 'ffmpeg' found. "
            "hyperframes may be a global executable on PATH, or a per-project "
            "npm install configured via 'cli_path' (absolute path to the "
            "hyperframes executable or dist/cli.js) or 'cli_command' "
            "(e.g. ['npx', 'hyperframes'] or ['node', '/abs/dist/cli.js']). "
            "Install hyperframes (npm/pip), configure one of these keys, "
            "or install ffmpeg for fallback rendering.",
        )

    def _target_size(self, assets: dict[str, Any]) -> tuple[int, int]:
        """Resolve the output frame size for this render (#378).

        Priority:

        1. ``assets["width"]/["height"]`` — the platform media spec, stamped on
           the assets by the runner (douyin/weibo/kuaishou are 1080x1920).
        2. The engine config block (``engines.video.hyperframes.width/height``)
           — an explicit operator override.
        3. 1080p landscape.

        Before this, only (2) and (3) existed, so every run produced 16:9 no
        matter which platform the brand was targeting.
        """
        raw_width = assets.get("width") or self._config.get("width", 1920)
        raw_height = assets.get("height") or self._config.get("height", 1080)
        return int(raw_width), int(raw_height)

    # ------------------------------------------------------------------
    # Render — primary hyperframes path → FFmpeg fallback
    # ------------------------------------------------------------------

    def render(self, assets: dict[str, Any], output_path: str) -> str:
        """Render a video from *assets* and write it to *output_path*.

        Parameters
        ----------
        assets:
            Dictionary with the following keys:

            - ``images`` (:class:`list[str]`): Paths to image files for video
              frames.  **Must not be empty.**
            - ``audio`` (:class:`str`): Path to the audio track file.
            - ``subtitles`` (:class:`str`): Path to the subtitle file
              (SRT or ASS).
            - ``template_dir`` (:class:`str`): Path to the video template
              directory.
            - ``content`` (:class:`str`): The rendered text content for
              overlays.

        output_path:
            Path where the rendered video file should be written.

        Returns
        -------
        str
            The absolute path to the rendered video (same as *output_path*).

        Raises
        ------
        EngineExecutionError
            - If ``assets["images"]`` is empty.
            - If the primary ``hyperframes`` call fails and
              ``allow_degrade`` is disabled (the failure propagates — no
              slideshow is written behind the caller's back, #414).
            - If degrade is enabled but the primary call fails and ``ffmpeg``
              is not available for the fallback.
            - If the FFmpeg fallback itself fails.
        """
        images: list[str] = assets.get("images", [])

        if not images:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details="Cannot render video: no images provided in assets.",
            )

        self.last_render_degraded = False
        self.last_render_reason = ""
        degrade = self._degrade_allowed()

        # Try the primary path first
        cli_base: list[str] | None = self._resolve_cli_base()
        if cli_base:
            try:
                return self._render_with_hyperframes(assets, output_path, cli_base)
            except EngineExecutionError as exc:
                # Keep the real failure in the log (#383).  A bare "render
                # failed" warning left no way to tell a missing browser from a
                # bad template from a timeout — and the fallback output looked
                # like a success on disk.
                self.last_render_degraded = True
                self.last_render_reason = str(exc)
                if not degrade:
                    logger.warning(
                        "hyperframes render failed; slideshow degrade is disabled "
                        "(engines.video.hyperframes.allow_degrade) — failing the "
                        "render instead of writing a slideshow (#414). reason=%s",
                        str(exc),
                    )
                    raise
                logger.warning(
                    "hyperframes render failed; falling back to the FFmpeg slideshow "
                    "(degraded output: still frame + audio). reason=%s",
                    str(exc),
                )

        if not degrade:
            # Degrade disabled and no primary failure to re-raise: the CLI was
            # never found. Fail loudly rather than silently shipping a
            # slideshow (#414).
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(
                    "hyperframes CLI not found and slideshow degrade is disabled "
                    "(engines.video.hyperframes.allow_degrade). Install the "
                    "hyperframes CLI, configure cli_path/cli_command, or set "
                    "allow_degrade: true to accept a marked FFmpeg slideshow."
                ),
            )

        # Fallback: FFmpeg slideshow (opt-in via allow_degrade, #414)
        try:
            ffmpeg_path: str | None = find_tool("ffmpeg")
        except ToolPathError as exc:
            raise EngineExecutionError(engine_name=self.engine_name, details=str(exc)) from exc
        if ffmpeg_path:
            rendered = self._render_with_ffmpeg(assets, output_path)
            self.last_render_degraded = self.last_render_degraded or not cli_base
            if not cli_base:
                self.last_render_reason = "hyperframes CLI not found; FFmpeg slideshow used"
            logger.warning(
                "video rendered as a degraded FFmpeg slideshow (still frame + audio): %s",
                output_path,
            )
            return rendered

        # Neither worked and no fallback available
        raise EngineExecutionError(
            engine_name=self.engine_name,
            details=(
                "hyperframes CLI failed and 'ffmpeg' is not available on PATH. "
                "Install ffmpeg for fallback rendering, or fix the hyperframes "
                "invocation."
            ),
        )

    # ------------------------------------------------------------------
    # Primary path — HyperFrames CLI
    # ------------------------------------------------------------------

    def _render_with_hyperframes(
        self,
        assets: dict[str, Any],
        output_path: str,
        cli_base: list[str] | None = None,
    ) -> str:
        """Render via ``hyperframes`` CLI using a temporary project directory.

        Parameters
        ----------
        assets:
            Asset dictionary (see :meth:`render`).
        output_path:
            Final output path for the rendered video.
        cli_base:
            Resolved CLI prefix (see :meth:`_resolve_cli_base`).  Resolved
            from config when omitted.

        Returns
        -------
        str
            The absolute, resolved path to the rendered video.

        Raises
        ------
        EngineExecutionError
            If the ``hyperframes`` subprocess fails or times out.
        """
        resolved_base: list[str] | None = cli_base or self._resolve_cli_base()
        if not resolved_base:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(
                    "hyperframes CLI not found. Provide a global 'hyperframes' "
                    "on PATH or configure 'cli_path' / 'cli_command'."
                ),
            )
        temp_dir: str | None = None
        timeout: int = self._config.get("timeout", 300)
        try:
            temp_dir = tempfile.mkdtemp(prefix="hyperframes_")

            # Copy images into the temp directory
            images_dir: str = os.path.join(temp_dir, "images")
            os.makedirs(images_dir, exist_ok=True)
            for img_path in assets.get("images", []):
                shutil.copy2(img_path, images_dir)

            # Copy or provision template project files
            template_dir: str | None = assets.get("template_dir")
            audio_path: str | None = assets.get("audio")
            if template_dir and os.path.isdir(template_dir):
                # User-provided templates: copy every item to temp_dir root
                for _item in os.listdir(template_dir):
                    _src: str = os.path.join(template_dir, _item)
                    _dst: str = os.path.join(temp_dir, _item)
                    if os.path.isdir(_src):
                        shutil.copytree(_src, _dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(_src, _dst)
                # Copy audio to root (backward compatible for user templates)
                if audio_path and os.path.isfile(audio_path):
                    shutil.copy2(audio_path, temp_dir)
            else:
                # No template_dir: provision shipped default templates
                self._provision_default_hyperframes_project(temp_dir, assets)

            # Copy subtitles if provided
            subs_path: str | None = assets.get("subtitles")
            if subs_path and os.path.isfile(subs_path):
                shutil.copy2(subs_path, temp_dir)

            # Build the command — real CLI interface (v0.7.x):
            #   hyperframes render [OPTIONS] [DIR]
            # where DIR (the project directory) is a positional argument;
            # there is no --assets option.
            quality: str = self._config.get("quality", "high")

            cmd: list[str] = [
                *resolved_base,
                "render",
                "-q",
                quality,
                "-o",
                output_path,
                temp_dir,
            ]

            logger.info(
                "Running hyperframes render (quality=%s, output=%s, project=%s)",
                quality,
                output_path,
                temp_dir,
            )

            env = os.environ.copy()
            chrome_path = self._config.get("chrome_path")
            if chrome_path and os.path.isfile(chrome_path):
                env["HYPERFRAMES_BROWSER_PATH"] = chrome_path

            result: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603  # cmd is hardcoded
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

            if result.returncode != 0:
                raise EngineExecutionError(
                    engine_name=self.engine_name,
                    details=(
                        f"hyperframes render failed (exit code {result.returncode}).\n"
                        f"stdout: {result.stdout}\n"
                        f"stderr: {result.stderr}"
                    ),
                )

            logger.info("hyperframes render succeeded (%s)", output_path)

            return os.path.abspath(output_path)

        except subprocess.TimeoutExpired:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(f"hyperframes render timed out after {timeout} seconds."),
            ) from None
        except EngineExecutionError:
            raise
        except Exception as exc:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=f"Unexpected error during hyperframes render: {exc}",
                cause=exc,
            ) from exc
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Fallback path — FFmpeg slideshow
    # ------------------------------------------------------------------

    def _render_with_ffmpeg(self, assets: dict[str, Any], output_path: str) -> str:
        """Render a video via an ``ffmpeg`` slideshow pipeline.

        Two-step process:

        1. Build an intermediate video from the image sequence.
        2. Mux the audio track onto the final output.

        Parameters
        ----------
        assets:
            Asset dictionary (see :meth:`render`).
        output_path:
            Final output path for the rendered video.

        Returns
        -------
        str
            The absolute, resolved path to the rendered video.

        Raises
        ------
        EngineExecutionError
            If either FFmpeg subprocess fails or times out.
        """
        temp_dir: str | None = None
        concat_path: str | None = None
        timeout: int = self._config.get("timeout", 300)
        try:
            temp_dir = tempfile.mkdtemp(prefix="ffmpeg_slideshow_")
            temp_video: str = os.path.join(temp_dir, "temp_video.mp4")

            # Per-scene assets win when the runner produced them (#389): the
            # slideshow then shows the six real scene pictures instead of
            # looping one cover/fallback frame for the whole narration, which
            # is what made every degraded render look like a still image with
            # a soundtrack.
            images: list[str] = list(assets.get("scene_media") or assets.get("images", []))
            audio: str | None = assets.get("audio")
            output_framerate: int = self._OUTPUT_FRAMERATE
            video_codec: str = self._VIDEO_CODEC

            # Target resolution: platform spec > engine config > 1080p (#378).
            width, height = self._target_size(assets)

            # Derive the input framerate from the real audio duration so the
            # slideshow's total length matches the narration.  With N images
            # at ``N / duration`` fps each image occupies ``duration / N``
            # seconds, giving exactly ``duration`` seconds overall.  Fall back
            # to the legacy 0.5 fps when the audio is missing or unprobeable.
            audio_duration: float | None = self._get_audio_duration(audio) if audio else None
            image_count: int = len(images)
            if audio_duration is not None and audio_duration > 0 and image_count > 0:
                input_framerate: float = image_count / audio_duration
            else:
                input_framerate = self._FALLBACK_FRAMERATE

            # Letterbox into the exact target size: scale down preserving
            # aspect ratio, then pad the remaining area symmetrically.
            video_filter: str = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            )

            # Step 1: Build slideshow video from images.
            if image_count == 1:
                # A single file cannot be expressed as a glob sequence (the
                # image2 glob demuxer emits only ~2s); loop it instead and
                # bound the loop with an explicit duration.
                loop_duration: float = (
                    audio_duration
                    if audio_duration is not None and audio_duration > 0
                    else float(self._DEFAULT_SCENE_DURATION)
                )
                slide_source: str = images[0]
                step1_cmd: list[str] = [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-framerate",
                    str(input_framerate),
                    "-i",
                    images[0],
                    "-t",
                    str(loop_duration),
                    "-vf",
                    video_filter,
                    "-c:v",
                    video_codec,
                    "-r",
                    str(output_framerate),
                    "-pix_fmt",
                    "yuv420p",
                    temp_video,
                ]
            else:
                # Concat demuxer instead of ``-pattern_type glob``: globbing
                # is not compiled into Windows libavformat builds ("Pattern
                # type 'glob' was selected but globbing is not supported by
                # this libavformat build"), which made every degraded render
                # fail outright on Windows (issue #505).  The explicit list
                # also tolerates non-contiguous filenames (scene 1 may reuse
                # the cover) that a ``%02d`` sequence pattern cannot express.
                # Per-image duration is ``1 / input_framerate`` so N images
                # still total ``N / framerate`` seconds, matching the audio;
                # the final entry repeats the last file with no duration
                # because the concat demuxer ignores the last file's own
                # duration directive.  The list lives in a real ``mkstemp``
                # file (not under ``temp_dir``) so the mocked-mkdtemp unit
                # tests and the real cleanup share one story: the file is
                # removed again in the ``finally`` below.
                per_image: float = (
                    1.0 / input_framerate
                    if input_framerate > 0
                    else float(self._DEFAULT_SCENE_DURATION)
                )
                fd, concat_path = tempfile.mkstemp(suffix=".txt", prefix="slideshow_")
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    for img in images:
                        # Forward slashes keep the list portable across
                        # POSIX/Windows; single quotes guard spaces.
                        fh.write(f"file '{os.path.abspath(img).replace(os.sep, '/')}'\n")
                        fh.write(f"duration {per_image:.6f}\n")
                    fh.write(f"file '{os.path.abspath(images[-1]).replace(os.sep, '/')}'\n")
                slide_source = concat_path
                step1_cmd = [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    concat_path,
                    "-vf",
                    video_filter,
                    "-c:v",
                    video_codec,
                    "-r",
                    str(output_framerate),
                    "-pix_fmt",
                    "yuv420p",
                    temp_video,
                ]

            logger.info(
                "Running FFmpeg slideshow (step 1/2) (source=%s, temp=%s)",
                slide_source,
                temp_video,
            )

            result1: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603  # step1_cmd is hardcoded
                step1_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result1.returncode != 0:
                raise EngineExecutionError(
                    engine_name=self.engine_name,
                    details=(
                        f"FFmpeg slideshow step 1 (build video) failed "
                        f"(exit code {result1.returncode}).\n"
                        f"stdout: {result1.stdout}\n"
                        f"stderr: {result1.stderr}"
                    ),
                )

            # Step 2: Mux audio onto the video (if audio is provided)
            if audio and os.path.isfile(audio):
                step2_cmd: list[str] = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_video,
                    "-i",
                    audio,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    output_path,
                ]

                logger.info(
                    "Running FFmpeg audio mux (step 2/2) (audio=%s, output=%s)",
                    audio,
                    output_path,
                )

                result2: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603  # step2_cmd is hardcoded
                    step2_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if result2.returncode != 0:
                    raise EngineExecutionError(
                        engine_name=self.engine_name,
                        details=(
                            f"FFmpeg audio mux step 2 failed "
                            f"(exit code {result2.returncode}).\n"
                            f"stdout: {result2.stdout}\n"
                            f"stderr: {result2.stderr}"
                        ),
                    )
            else:
                # No audio track — just move the temp video to the output path
                logger.info("No audio track provided; skipping audio mux step.")
                shutil.move(temp_video, output_path)

            logger.info("FFmpeg slideshow render succeeded (%s)", output_path)
            return os.path.abspath(output_path)

        except subprocess.TimeoutExpired:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(f"FFmpeg slideshow render timed out after {timeout} seconds."),
            ) from None
        except EngineExecutionError:
            raise
        except Exception as exc:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=f"Unexpected error during FFmpeg slideshow render: {exc}",
                cause=exc,
            ) from exc
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            if concat_path is not None:
                with contextlib.suppress(OSError):
                    os.remove(concat_path)

    # ------------------------------------------------------------------
    # Audio duration detection (for default template provisioning)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float | None:
        """Detect audio duration using ``ffprobe`` (seconds, or ``None`` on failure)."""
        try:
            ffprobe: str | None = find_tool("ffprobe")
        except ToolPathError:
            return None
        if not ffprobe or not audio_path or not os.path.isfile(audio_path):
            return None
        try:
            result: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603  # ffprobe path is hardcoded
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
        return None

    # ------------------------------------------------------------------
    # Default template provisioning
    # ------------------------------------------------------------------

    @staticmethod
    def _gsap_in_dir(directory: str) -> str | None:
        """Return ``gsap.min.js``/``gsap.js`` under *directory*, or ``None``."""
        for filename in ("gsap.min.js", "gsap.js"):
            candidate = os.path.join(directory, filename)
            if os.path.isfile(candidate):
                return candidate
        return None

    @classmethod
    def _gsap_in_node_modules(cls, node_modules: str) -> str | None:
        """Search a ``node_modules`` tree for a bundled or standalone gsap."""
        import glob as _glob

        vendor_dirs = _glob.glob(
            os.path.join(node_modules, "hyperframes", "dist", "vendor", "npm", "gsap@*", "dist")
        )
        for vendor_dir in sorted(vendor_dirs):
            hit = cls._gsap_in_dir(vendor_dir)
            if hit is not None:
                return hit
        return cls._gsap_in_dir(os.path.join(node_modules, "gsap", "dist"))

    def _locate_gsap(self, assets: dict[str, Any], resolved_cli_dir: str | None) -> str | None:
        """Find a local gsap copy so renders work without CDN access.

        Priority: ``assets["gsap_path"]`` > ``self._config["gsap_path"]`` >
        the hyperframes CLI's bundled copy > a local npm layout (walking up
        from the resolved CLI) > ``npm root -g`` > the current working
        directory. Both ``dist/gsap.min.js`` and ``dist/gsap.js`` are
        accepted. ``None`` keeps the CDN reference in the templates.
        """
        import glob as _glob

        hit: str | None
        explicit: Any = assets.get("gsap_path")
        if explicit and os.path.isfile(str(explicit)):
            hit = str(explicit)
            logger.info("Using local gsap: %s", hit)
            return hit

        configured: Any = self._config.get("gsap_path")
        if configured and os.path.isfile(str(configured)):
            hit = str(configured)
            logger.info("Using local gsap: %s", hit)
            return hit

        searched: list[str] = []

        # Existing CLI-bundled vendor glob (kept unchanged).
        cli_base = self._resolve_cli_base() or []
        for part in cli_base:
            if os.path.isfile(part) or part.endswith(".js"):
                cli_dir = os.path.dirname(os.path.abspath(part))
                for base in (
                    os.path.join(cli_dir, "..", "lib", "node_modules", "hyperframes"),
                    os.path.join(cli_dir, "..", "..", "hyperframes"),
                ):
                    searched.append(base)
                    for pattern in ("gsap.min.js", "gsap.js"):
                        for hit in _glob.glob(
                            os.path.join(base, "dist", "vendor", "npm", "gsap@*", "dist", pattern)
                        ):
                            logger.info("Using local gsap: %s", hit)
                            return hit

        # Local npm installs: walk up from the resolved CLI binary.
        which_path: str | None = shutil.which("hyperframes")
        if which_path:
            current = os.path.dirname(os.path.realpath(which_path))
            for _ in range(7):
                searched.append(current)
                hit = self._gsap_in_node_modules(os.path.join(current, "node_modules"))
                if hit is not None:
                    logger.info("Using local gsap: %s", hit)
                    return hit
                parent = os.path.dirname(current)
                if parent == current:
                    break
                current = parent

        # Global npm root (quietly skip when npm is missing or errors).
        try:
            npm_result = subprocess.run(
                ["npm", "root", "-g"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            npm_result = None
        if npm_result is not None and npm_result.returncode == 0:
            npm_root = npm_result.stdout.strip()
            if npm_root:
                searched.append(npm_root)
                hit = self._gsap_in_dir(os.path.join(npm_root, "gsap", "dist"))
                if hit is not None:
                    logger.info("Using local gsap: %s", hit)
                    return hit

        # Finally, the current working directory.
        cwd = os.getcwd()
        searched.append(cwd)
        hit = self._gsap_in_dir(os.path.join(cwd, "node_modules", "gsap", "dist"))
        if hit is not None:
            logger.info("Using local gsap: %s", hit)
            return hit

        logger.warning(
            "No local gsap found; searched: %s",
            ", ".join(dict.fromkeys(searched)),
        )
        return None

    def _apply_frame_size(self, project_config_path: str, assets: dict[str, Any]) -> None:
        """Write the resolved frame size into a provisioned project's config.

        Keeps every other key of the shipped ``hyperframes.json`` untouched —
        only ``project.width`` / ``project.height`` (and ``fps`` when the spec
        states one) are rewritten.
        """
        if not os.path.isfile(project_config_path):
            return
        try:
            with open(project_config_path, encoding="utf-8") as fh:
                config = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s to set the frame size: %s", project_config_path, exc)
            return

        width, height = self._target_size(assets)
        project = config.setdefault("project", {})
        project["width"] = width
        project["height"] = height
        fps = assets.get("fps") or self._config.get("fps")
        if fps:
            project["fps"] = int(fps)

        with open(project_config_path, "w", encoding="utf-8") as fh:
            json.dump(config, fh, ensure_ascii=False, indent=2)
        logger.info("hyperframes project frame size set to %dx%d", width, height)

    def _provision_default_hyperframes_project(self, temp_dir: str, assets: dict[str, Any]) -> None:
        """Provision a complete hyperframes project from shipped default templates.

        Copies static files (``hyperframes.json``, ``package.json``), renders
        Jinja2 templates (``index.html``, ``meta.json``, scene compositions),
        and sets up ``assets/audio/``.

        Called automatically when ``assets["template_dir"]`` is empty/falsy.
        """
        import importlib.resources

        _templates = importlib.resources.files("automedia.templates.hyperframes")

        # 1. Copy static template files to temp_dir root
        for _filename in ("hyperframes.json", "package.json"):
            _src_path = _templates.joinpath(_filename)
            if _src_path.is_file():
                shutil.copy2(str(_src_path), temp_dir)

        # 1a. Apply the target frame size to the project config (#378).  The
        # shipped ``hyperframes.json`` hardcodes 1920x1080, so copying it
        # verbatim forced every render to 16:9 — a douyin/weibo run shipped a
        # landscape video.  A user-supplied ``template_dir`` keeps its own
        # config: that project owns its composition size.
        self._apply_frame_size(os.path.join(temp_dir, "hyperframes.json"), assets)

        # 1b. Vendor GSAP when a local copy is available (#351): CDN access is
        # unreliable in some networks (jsdelivr resets connections), and the
        # hyperframes render blocks on timeline-script failures. Priority:
        # assets["gsap_path"] > the CLI's own bundled copy > CDN fallback.
        gsap_src = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
        gsap_local = self._locate_gsap(assets, resolved_cli_dir=None)
        if gsap_local is not None:
            vendor_dir = os.path.join(temp_dir, "assets", "vendor")
            os.makedirs(vendor_dir, exist_ok=True)
            shutil.copy2(gsap_local, os.path.join(vendor_dir, "gsap.min.js"))
            gsap_src = "assets/vendor/gsap.min.js"
            logger.info("Provisioned project vendors gsap from %s", gsap_local)

        # 2. Detect audio duration and set up scene parameters
        images: list[str] = assets.get("images", [])
        audio_path: str | None = assets.get("audio")
        content_text: str = assets.get("content", "")
        timeline_scenes: list[dict[str, Any]] = list(assets.get("scenes") or [])
        scene_media: list[str] = list(assets.get("scene_media") or [])
        num_scenes: int = len(timeline_scenes) if timeline_scenes else len(images)
        total_duration: float = 0.0
        audio_basename: str = ""

        if timeline_scenes:
            # Narration-aligned timeline (#351): the timeline's per-scene
            # durations ARE the truth (measured where ffprobe lives) — do not
            # re-probe locally, a machine without ffprobe would fall back to
            # defaults and desync audio from the scene cuts.
            total_duration = sum(float(s.get("duration", 0.0)) for s in timeline_scenes)
        if audio_path and os.path.isfile(audio_path) and total_duration <= 0:
            audio_basename = os.path.basename(audio_path)
            audio_dir: str = os.path.join(temp_dir, "assets", "audio")
            os.makedirs(audio_dir, exist_ok=True)
            shutil.copy2(audio_path, audio_dir)
            detected: float | None = self._get_audio_duration(audio_path)
            if detected is not None and detected > 0:
                total_duration = detected
            else:
                total_duration = num_scenes * self._DEFAULT_SCENE_DURATION
        elif audio_path and os.path.isfile(audio_path):
            audio_basename = os.path.basename(audio_path)
            audio_dir = os.path.join(temp_dir, "assets", "audio")
            os.makedirs(audio_dir, exist_ok=True)
            shutil.copy2(audio_path, audio_dir)
        else:
            total_duration = total_duration or num_scenes * self._DEFAULT_SCENE_DURATION

        # 3. Build the scene list. Two sources:
        #    - narration-aligned timeline (assets["scenes"], #351): real
        #      per-scene durations (cut points = sentence ends) and per-scene
        #      text; scene media comes from assets["scene_media"].
        #    - legacy proportional split over the images (no timeline).
        scenes: list[dict[str, Any]] = []
        if timeline_scenes:
            for s in timeline_scenes:
                text_s = str(s.get("text", "") or "")
                title_s = re.split(r"[。！？!?；;\n]", text_s, maxsplit=1)[0].strip()
                scenes.append(
                    {
                        "id": str(s.get("id", f"scene-{s.get('index', len(scenes) + 1)}")),
                        "index": int(s.get("index", len(scenes) + 1)),
                        "start": float(s.get("start", 0.0)),
                        "duration": float(s.get("duration", 0.0)) or 3.0,
                        "name": title_s[:24] or f"Scene {s.get('index', '')}",
                        "content": text_s,
                        "media_src": "",
                    }
                )
            media_dir: str = os.path.join(temp_dir, "images")
            os.makedirs(media_dir, exist_ok=True)
            for i, scene in enumerate(scenes):
                media = scene_media[i] if i < len(scene_media) else ""
                if media and os.path.isfile(media):
                    shutil.copy2(media, os.path.join(media_dir, os.path.basename(media)))
                    scene["media_src"] = f"../images/{os.path.basename(media)}"
        else:
            duration_per_scene: float = (
                max(3.0, total_duration / num_scenes) if num_scenes > 0 else 0.0
            )
            for i in range(num_scenes):
                start: float = round(i * duration_per_scene, 1)
                dur: float = round(duration_per_scene, 1)
                if i == num_scenes - 1:
                    dur = round(total_duration - start, 1)
                scenes.append(
                    {
                        "id": f"scene-{i + 1}",
                        "index": i + 1,
                        "start": start,
                        "duration": dur,
                        "name": f"Scene {i + 1}",
                        "content": content_text,
                        "media_src": f"../images/{os.path.basename(images[i])}" if images else "",
                    }
                )

        # 4. Create compositions directory
        compositions_dir: str = os.path.join(temp_dir, "compositions")
        os.makedirs(compositions_dir, exist_ok=True)

        # 5. Render and write index.html
        _index_tpl = jinja2.Template(
            _templates.joinpath("index.html.j2").read_text(encoding="utf-8"),
        )
        index_html: str = _index_tpl.render(
            total_duration=total_duration,
            audio_basename=audio_basename,
            scenes=scenes,
            gsap_src=gsap_src,
        )
        with open(os.path.join(temp_dir, "index.html"), "w", encoding="utf-8") as _f:
            _f.write(index_html)

        # 6. Render and write meta.json
        _meta_tpl = jinja2.Template(
            _templates.joinpath("meta.json.j2").read_text(encoding="utf-8"),
        )
        scene_data: list[dict[str, Any]] = [
            {
                "id": s["id"],
                "name": s["name"],
                "start": s["start"],
                "duration": s["duration"],
            }
            for s in scenes
        ]
        meta_json: str = _meta_tpl.render(
            title=assets.get("title", "AutoMedia Video"),
            description=assets.get("description", "Generated by AutoMedia pipeline"),
            total_duration=total_duration,
            created_at=date.today().isoformat(),
            scenes_json=json.dumps(scene_data, indent=2, ensure_ascii=False),
        )
        with open(os.path.join(temp_dir, "meta.json"), "w", encoding="utf-8") as _f:
            _f.write(meta_json)

        # 7. Render and write scene compositions
        _scene_tpl = jinja2.Template(
            _templates.joinpath("scene.html.j2").read_text(encoding="utf-8"),
        )
        brand_line = str(assets.get("brand_line", "") or "AutoMedia")
        for scene in scenes:
            scene_html: str = _scene_tpl.render(
                scene_id=scene["id"],
                duration=scene["duration"],
                title=scene["name"],
                content=scene["content"],
                media_src=scene.get("media_src", ""),
                brand_line=brand_line,
                scene_index=scene["index"],
                total_scenes=len(scenes),
                gsap_src="../" + gsap_src if gsap_src.startswith("assets/") else gsap_src,
            )
            scene_path: str = os.path.join(
                compositions_dir,
                f"{scene['index']:02d}-scene.html",
            )
            with open(scene_path, "w", encoding="utf-8") as _f:
                _f.write(scene_html)

        logger.info(
            "Provisioned default hyperframes project (%d scenes, %.1fs total) in %s",
            num_scenes,
            total_duration,
            temp_dir,
        )
