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

import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import date
from typing import Any, ClassVar

import jinja2

from automedia.engines.base import BaseVideoEngine
from automedia.engines.errors import EngineExecutionError

logger = logging.getLogger(__name__)


class HyperFramesVideoEngine(BaseVideoEngine):
    """Render a video from images, audio, and subtitles.

    **Primary path** — ``hyperframes`` CLI:

    1. Copy all assets into a temporary working directory.
    2. Invoke ``hyperframes render --quality <quality> --assets <dir> --output <path>``.
    3. On success return ``output_path``.
    4. On failure, if ``ffmpeg`` is available, fall back to the FFmpeg
       slideshow path.

    **Fallback path** — ``ffmpeg`` slideshow:

    1. Build a slideshow video from the image sequence.
    2. Mux the audio track onto the result.
    3. Write the final file to ``output_path``.

    **When both tools are absent**, :meth:`check_available` returns
    ``(False, ...)``.  If the engine is used anyway, :meth:`render` raises
    :class:`EngineExecutionError`.
    """

    engine_name: ClassVar[str] = "hyperframes"
    modality: ClassVar[str] = "video"

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

    def check_available(self) -> tuple[bool, str]:
        """Verify that at least one of ``hyperframes`` or ``ffmpeg`` is on ``PATH``.

        Returns
        -------
        tuple[bool, str]
            ``(True, ...)`` if either tool is found; ``(False, ...)`` only
            when neither is available.
        """
        hyperframes_path: str | None = shutil.which("hyperframes")
        ffmpeg_path: str | None = shutil.which("ffmpeg")

        if hyperframes_path:
            return (True, f"hyperframes found at {hyperframes_path}")

        if ffmpeg_path:
            return (True, f"hyperframes not found; ffmpeg fallback at {ffmpeg_path}")

        return (
            False,
            "Neither 'hyperframes' nor 'ffmpeg' found on PATH. "
            "Install hyperframes (npm/pip) or ffmpeg to use this engine.",
        )

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
            - If the primary ``hyperframes`` call fails and ``ffmpeg`` is not
              available for the fallback.
            - If the FFmpeg fallback itself fails.
        """
        images: list[str] = assets.get("images", [])

        if not images:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details="Cannot render video: no images provided in assets.",
            )

        # Try the primary path first
        hyperframes_path: str | None = shutil.which("hyperframes")
        if hyperframes_path:
            try:
                return self._render_with_hyperframes(assets, output_path)
            except EngineExecutionError:
                logger.warning(
                    "hyperframes render failed; checking for ffmpeg fallback."
                )

        # Fallback: FFmpeg slideshow
        ffmpeg_path: str | None = shutil.which("ffmpeg")
        if ffmpeg_path:
            return self._render_with_ffmpeg(assets, output_path)

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
        self, assets: dict[str, Any], output_path: str
    ) -> str:
        """Render via ``hyperframes`` CLI using a temporary asset directory.

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
            If the ``hyperframes`` subprocess fails or times out.
        """
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

            # Build the command
            quality: str = self._config.get("quality", "high")

            cmd: list[str] = [
                "hyperframes",
                "render",
                "--quality", quality,
                "--assets", temp_dir,
                "--output", output_path,
            ]

            logger.info(
                "Running hyperframes render (quality=%s, output=%s, assets=%s)",
                quality,
                output_path,
                temp_dir,
            )

            env = os.environ.copy()
            chrome_path = self._config.get("chrome_path")
            if chrome_path and os.path.isfile(chrome_path):
                env["HYPERFRAMES_BROWSER_PATH"] = chrome_path

            result: subprocess.CompletedProcess[str] = subprocess.run(
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
                details=(
                    f"hyperframes render timed out after {timeout} seconds."
                ),
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

    def _render_with_ffmpeg(
        self, assets: dict[str, Any], output_path: str
    ) -> str:
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
        timeout: int = self._config.get("timeout", 300)
        try:
            temp_dir = tempfile.mkdtemp(prefix="ffmpeg_slideshow_")
            temp_video: str = os.path.join(temp_dir, "temp_video.mp4")

            images: list[str] = assets.get("images", [])
            audio: str | None = assets.get("audio")
            fallback_framerate: float = self._FALLBACK_FRAMERATE
            output_framerate: int = self._OUTPUT_FRAMERATE
            video_codec: str = self._VIDEO_CODEC

            # Step 1: Build slideshow video from images
            # Use the first image's directory as the glob root
            images_dir: str = os.path.dirname(images[0]) if images else ""
            glob_pattern: str = os.path.join(images_dir, "*.png")

            # Determine the actual image extension from the first image
            first_img: str = images[0]
            img_ext: str = os.path.splitext(first_img)[1] or ".png"
            glob_pattern = os.path.join(images_dir, f"*{img_ext}")

            step1_cmd: list[str] = [
                "ffmpeg",
                "-y",
                "-framerate", str(fallback_framerate),
                "-pattern_type", "glob",
                "-i", glob_pattern,
                "-c:v", video_codec,
                "-r", str(output_framerate),
                "-pix_fmt", "yuv420p",
                temp_video,
            ]

            logger.info(
                "Running FFmpeg slideshow (step 1/2) (glob=%s, temp=%s)",
                glob_pattern,
                temp_video,
            )

            result1: subprocess.CompletedProcess[str] = subprocess.run(
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
                    "-i", temp_video,
                    "-i", audio,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path,
                ]

                logger.info(
                    "Running FFmpeg audio mux (step 2/2) (audio=%s, output=%s)",
                    audio,
                    output_path,
                )

                result2: subprocess.CompletedProcess[str] = subprocess.run(
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
                details=(
                    f"FFmpeg slideshow render timed out after {timeout} seconds."
                ),
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

    # ------------------------------------------------------------------
    # Audio duration detection (for default template provisioning)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float | None:
        """Detect audio duration using ``ffprobe`` (seconds, or ``None`` on failure)."""
        ffprobe: str | None = shutil.which("ffprobe")
        if not ffprobe or not audio_path or not os.path.isfile(audio_path):
            return None
        try:
            result: subprocess.CompletedProcess[str] = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],  # noqa: S603
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

    def _provision_default_hyperframes_project(
        self, temp_dir: str, assets: dict[str, Any]
    ) -> None:
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

        # 2. Detect audio duration and set up scene parameters
        images: list[str] = assets.get("images", [])
        audio_path: str | None = assets.get("audio")
        content_text: str = assets.get("content", "")
        num_scenes: int = len(images)
        total_duration: float = 0.0
        audio_basename: str = ""

        if audio_path and os.path.isfile(audio_path):
            audio_basename = os.path.basename(audio_path)
            audio_dir: str = os.path.join(temp_dir, "assets", "audio")
            os.makedirs(audio_dir, exist_ok=True)
            shutil.copy2(audio_path, audio_dir)
            detected: float | None = self._get_audio_duration(audio_path)
            if detected is not None and detected > 0:
                total_duration = detected
            else:
                total_duration = num_scenes * self._DEFAULT_SCENE_DURATION
        else:
            total_duration = num_scenes * self._DEFAULT_SCENE_DURATION

        # 3. Build scene list with proportional timing
        duration_per_scene: float = (
            max(3.0, total_duration / num_scenes) if num_scenes > 0 else 0.0
        )
        scenes: list[dict[str, Any]] = []
        for i in range(num_scenes):
            start: float = round(i * duration_per_scene, 1)
            dur: float = round(duration_per_scene, 1)
            if i == num_scenes - 1:
                dur = round(total_duration - start, 1)
            scenes.append({
                "id": f"scene-{i + 1}",
                "index": i + 1,
                "start": start,
                "duration": dur,
                "name": f"Scene {i + 1}",
                "image": os.path.basename(images[i]) if images else "",
                "content": content_text,
            })

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
        for scene in scenes:
            scene_html: str = _scene_tpl.render(
                scene_id=scene["id"],
                duration=scene["duration"],
                title=scene["name"],
                content=scene["content"],
            )
            scene_path: str = os.path.join(
                compositions_dir, f"{scene['index']:02d}-scene.html",
            )
            with open(scene_path, "w", encoding="utf-8") as _f:
                _f.write(scene_html)

        logger.info(
            "Provisioned default hyperframes project (%d scenes, %.1fs total) in %s",
            num_scenes, total_duration, temp_dir,
        )
