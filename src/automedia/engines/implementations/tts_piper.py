"""Piper TTS engine — local, offline text-to-speech via ``piper-tts``.

Provides:
    - :class:`PiperTTSEngine` — a :class:`BaseTTSEngine` implementation that
      runs the Piper ONNX voice model in-process and (optionally) transcodes
      the result to MP3 with ``ffmpeg``.

The engine degrades gracefully: importing this module never imports
``piper``.  The dependency is only touched inside :meth:`check_available`
and :meth:`synthesize`, so a missing ``piper-tts`` install cannot break
``import automedia``.

Model path resolution order:

1. ``config["engines"]["tts"]["piper"]["model_path"]``
2. ``AUTOMEDIA_PIPER_MODEL_PATH`` (real env, then ``.env`` overlay)
3. ``AUTOMEDIA_PIPER_MODEL`` (legacy alias, same lookup)
4. ``None`` — the engine reports itself unavailable.

Usage::

    engine = PiperTTSEngine({"model_path": "/models/zh.onnx"})
    path = engine.synthesize("你好世界", voice="", output_path="/tmp/out.mp3")
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import tempfile
import wave
from typing import TYPE_CHECKING, Any, ClassVar

from typing_extensions import override

from automedia.core.env_overlay import env_lookup
from automedia.engines.base import BaseTTSEngine
from automedia.engines.errors import EngineExecutionError

if TYPE_CHECKING:
    from piper import PiperVoice, SynthesisConfig

#: Primary environment variable consulted when no ``model_path`` config is set.
MODEL_PATH_ENV_VAR = "AUTOMEDIA_PIPER_MODEL_PATH"
#: Legacy environment variable, kept as a secondary fallback.
LEGACY_MODEL_ENV_VAR = "AUTOMEDIA_PIPER_MODEL"

DEFAULT_BITRATE = 192
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_SPEAKER = 0
DEFAULT_LENGTH_SCALE = 1.0


class PiperTTSEngine(BaseTTSEngine):
    """Offline TTS engine backed by Piper ONNX voices."""

    engine_name: ClassVar[str] = "piper"
    modality: ClassVar[str] = "tts"

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _resolve_model_path(self) -> str | None:
        """Return the configured Piper voice model path, if any."""
        raw = (
            self._config.get("model_path")
            or env_lookup(MODEL_PATH_ENV_VAR)
            or env_lookup(LEGACY_MODEL_ENV_VAR)
        )
        if not raw:
            return None
        return os.path.expanduser(str(raw))

    def _speaker(self) -> int:
        """Return the configured speaker id (default ``0``)."""
        raw = self._config.get("speaker", DEFAULT_SPEAKER)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return DEFAULT_SPEAKER

    def _length_scale(self) -> float:
        """Return the configured speaking-rate scale (default ``1.0``)."""
        raw = self._config.get("length_scale", DEFAULT_LENGTH_SCALE)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return DEFAULT_LENGTH_SCALE
        return value if value > 0 else DEFAULT_LENGTH_SCALE

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @override
    def check_available(self) -> tuple[bool, str]:
        """Check that ``piper`` imports and the configured model exists."""
        try:
            import piper  # noqa: F401  # import probe only
        except Exception as exc:  # pragma: no cover - environment dependent
            return False, f"piper is not installed: {exc}"

        model_path = self._resolve_model_path()
        if not model_path:
            return (
                False,
                "no piper model configured (set engines.tts.piper.model_path, "
                f"{MODEL_PATH_ENV_VAR}, or {LEGACY_MODEL_ENV_VAR})",
            )
        if not os.path.isfile(model_path):
            return False, f"piper model not found: {model_path}"
        return True, ""

    @override
    def validate_config(self) -> None:
        """Require a ``model_path`` that exists on disk."""
        model_path = self._resolve_model_path()
        if not model_path:
            raise ValueError(
                "piper model_path is required (set engines.tts.piper.model_path, "
                f"{MODEL_PATH_ENV_VAR}, or {LEGACY_MODEL_ENV_VAR})"
            )
        if not os.path.isfile(model_path):
            raise ValueError(f"piper model_path not found: {model_path}")

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    @override
    def synthesize(
        self,
        text: str,
        voice: str = "",
        output_path: str = "",
    ) -> str:
        """Synthesize *text* into WAV or MP3.

        Args:
            text: Text to synthesize. Must be non-empty.
            voice: Ignored — Piper voices are single-speaker models selected
                by ``model_path``. Accepted for API compatibility.
            output_path: Destination path. When it ends with ``.mp3`` the
                WAV is transcoded with ffmpeg; otherwise WAV is written as-is.

        Returns:
            Absolute path to the generated audio file.

        Raises:
            ValueError: If *text*, *output_path* or the model path is missing.
            EngineExecutionError: If synthesis or transcoding fails.
        """
        if not text:
            raise ValueError("text must not be empty")
        if not output_path:
            raise ValueError("output_path must not be empty")

        model_path = self._resolve_model_path()
        if not model_path:
            raise ValueError(
                "piper model_path is not configured (set "
                f"engines.tts.piper.model_path, {MODEL_PATH_ENV_VAR}, "
                f"or {LEGACY_MODEL_ENV_VAR})"
            )

        output_abs = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_abs), exist_ok=True)

        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"piper is not installed: {exc}",
                cause=exc,
            ) from exc

        tmp_fd, tmp_wav = tempfile.mkstemp(suffix=".wav", prefix="automedia-piper-")
        os.close(tmp_fd)
        tmp_path: str | None = tmp_wav
        try:
            try:
                voice_model = PiperVoice.load(model_path)
                with wave.open(tmp_wav, "wb") as wav_file:
                    self._synthesize_to_wav(voice_model, text, wav_file)
            except EngineExecutionError:
                raise
            except Exception as exc:
                raise EngineExecutionError(
                    self.engine_name,
                    f"piper synthesis failed: {exc}",
                    cause=exc,
                ) from exc

            if output_abs.lower().endswith(".mp3"):
                self._transcode_to_mp3(tmp_wav, output_abs)
            else:
                shutil.move(tmp_wav, output_abs)
                tmp_path = None

            return output_abs
        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _synthesize_to_wav(
        self, voice_model: PiperVoice, text: str, wav_file: wave.Wave_write
    ) -> None:
        """Call ``synthesize_wav`` with the installed Piper's signature.

        Piper 1.2 exposes ``synthesize_wav(text, wav_file)``; newer releases
        accept a third ``SynthesisConfig`` argument.  Both shapes are handled
        without ever raising for unsupported keyword arguments.
        """
        syn_config = self._build_synthesis_config()
        if syn_config is None:
            voice_model.synthesize_wav(text, wav_file)
            return

        params = self._synthesize_wav_params(voice_model)
        if params is None or len(params) >= 3:
            voice_model.synthesize_wav(text, wav_file, syn_config)
        else:
            voice_model.synthesize_wav(text, wav_file)

    @staticmethod
    def _synthesize_wav_params(voice_model: PiperVoice) -> list[inspect.Parameter] | None:
        """Return the bound ``synthesize_wav`` parameters, or ``None``."""
        try:
            signature = inspect.signature(voice_model.synthesize_wav)
        except (TypeError, ValueError):
            return None
        return list(signature.parameters.values())

    def _build_synthesis_config(self) -> SynthesisConfig | None:
        """Build a Piper ``SynthesisConfig`` when the install supports it.

        Returns ``None`` when the installed ``piper`` has no
        ``SynthesisConfig`` or exposes none of the requested fields.  The
        construction is filtered against the dataclass signature so an
        unsupported field can never raise a ``TypeError``.
        """
        try:
            from piper import SynthesisConfig
        except ImportError:
            return None

        try:
            accepted = set(inspect.signature(SynthesisConfig).parameters)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None

        candidates: dict[str, Any] = {
            "speaker_id": self._speaker(),
            "speaker": self._speaker(),
            "length_scale": self._length_scale(),
        }
        kwargs = {key: value for key, value in candidates.items() if key in accepted}
        # ``speaker_id`` wins when both aliases exist.
        if "speaker_id" in kwargs and "speaker" in kwargs:
            kwargs.pop("speaker")
        if not kwargs:
            return None
        try:
            return SynthesisConfig(**kwargs)
        except TypeError:  # pragma: no cover - defensive against odd builds
            return None

    def _transcode_to_mp3(self, wav_path: str, output_path: str) -> None:
        """Transcode *wav_path* to mono MP3 at *output_path* with ffmpeg."""
        bitrate = self._config.get("bitrate", DEFAULT_BITRATE)
        sample_rate = self._config.get("sample_rate", DEFAULT_SAMPLE_RATE)
        try:
            bitrate_int = int(bitrate) if bitrate else DEFAULT_BITRATE
            sample_rate_int = int(sample_rate) if sample_rate else DEFAULT_SAMPLE_RATE
        except (TypeError, ValueError):
            bitrate_int = DEFAULT_BITRATE
            sample_rate_int = DEFAULT_SAMPLE_RATE

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            wav_path,
            "-c:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate_int}k",
            "-ar",
            str(sample_rate_int),
            "-ac",
            "1",
            output_path,
        ]
        try:
            result = subprocess.run(  # noqa: S603 — trusted internal command
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"ffmpeg transcoding failed: {exc}",
                cause=exc,
            ) from exc

        if result.returncode != 0:
            raise EngineExecutionError(
                self.engine_name,
                f"ffmpeg transcoding failed (rc={result.returncode}): {result.stderr}",
            )
