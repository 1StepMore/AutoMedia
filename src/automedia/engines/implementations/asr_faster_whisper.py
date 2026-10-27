"""faster-whisper ASR engine — local, offline speech recognition.

Provides:
    - :class:`FasterWhisperASREngine` — a :class:`BaseASREngine` implementation
      backed by the CTranslate2 ``faster-whisper`` package.

The dependency is imported lazily (never at module import time), so a
missing ``faster-whisper`` install cannot break ``import automedia``.

Model resolution order:

1. ``config["engines"]["asr"]["faster-whisper"]["model_path"]``
2. ``config["engines"]["asr"]["faster-whisper"]["model"]`` (legacy alias)
3. ``AUTOMEDIA_FASTER_WHISPER_MODEL`` (real env, then ``.env`` overlay)
4. ``"tiny"`` (a size name the library resolves/downloads on first use)

When the resolved value is an existing local *directory*, the model is
loaded from disk and no network download is attempted.

Language resolution: the *language* argument, then ``config["language"]``,
then ``"zh"``.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from typing_extensions import override

from automedia.core.env_overlay import env_lookup
from automedia.engines.base import BaseASREngine
from automedia.engines.errors import EngineExecutionError

#: Environment variable consulted when no model config is supplied.
MODEL_ENV_VAR = "AUTOMEDIA_FASTER_WHISPER_MODEL"

DEFAULT_MODEL = "tiny"
DEFAULT_LANGUAGE = "zh"
DEFAULT_COMPUTE_TYPE = "int8"


class FasterWhisperASREngine(BaseASREngine):
    """Offline ASR engine backed by ``faster-whisper``."""

    engine_name: ClassVar[str] = "faster-whisper"
    modality: ClassVar[str] = "asr"

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _resolve_model(self) -> str:
        """Return the configured model name or local directory."""
        raw = (
            self._config.get("model_path") or self._config.get("model") or env_lookup(MODEL_ENV_VAR)
        )
        if not raw:
            return DEFAULT_MODEL
        return os.path.expanduser(str(raw))

    def _configured_model(self) -> str | None:
        """Return an explicitly configured model value (no built-in default)."""
        raw = (
            self._config.get("model_path") or self._config.get("model") or env_lookup(MODEL_ENV_VAR)
        )
        if not raw:
            return None
        return os.path.expanduser(str(raw))

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @override
    def check_available(self) -> tuple[bool, str]:
        """Check that ``faster-whisper`` imports and any local model exists.

        Model presence is validated lazily at transcription time for bare
        size names (the library downloads them on first use).  A configured
        *path* that does not exist is reported unavailable rather than
        failing mid-pipeline.
        """
        try:
            import faster_whisper  # noqa: F401  # import probe only
        except Exception as exc:  # pragma: no cover - environment dependent
            return False, f"faster-whisper is not installed: {exc}"

        configured = self._configured_model()
        if configured:
            # A path-like value that does not exist is a hard config error;
            # a bare model name (e.g. "tiny") is resolved by the library.
            looks_like_path = os.path.isabs(configured) or os.sep in configured
            if looks_like_path and not os.path.isdir(configured):
                return False, f"faster-whisper model directory not found: {configured}"
        return True, ""

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    @override
    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe *audio_path* with a local CTranslate2 Whisper model.

        Args:
            audio_path: Path to the audio file.
            language: Source language code; falls back to config then ``"zh"``.

        Returns:
            ``{"text": str, "segments": [{"start": float, "end": float,
            "text": str}]}`` — exactly the shape
            :meth:`~automedia.pipelines.audio_pipeline.AudioPipeline.generate_srt`
            consumes.

        Raises:
            FileNotFoundError: If *audio_path* does not exist.
            EngineExecutionError: If the model cannot be loaded or
                transcription fails.
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"audio file not found: {audio_path}")

        lang = language or self._config.get("language") or DEFAULT_LANGUAGE
        model_name = self._resolve_model()
        device = self._config.get("device", "cpu")
        compute_type = self._config.get("compute_type", DEFAULT_COMPUTE_TYPE)

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"faster-whisper is not installed: {exc}",
                cause=exc,
            ) from exc

        try:
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            raw_segments, _info = model.transcribe(
                audio_path,
                language=lang,
                vad_filter=True,
            )
            segments: list[dict[str, Any]] = []
            texts: list[str] = []
            for segment in raw_segments:
                seg_text = str(getattr(segment, "text", "")).strip()
                segments.append(
                    {
                        "start": float(getattr(segment, "start", 0.0)),
                        "end": float(getattr(segment, "end", 0.0)),
                        "text": seg_text,
                    }
                )
                texts.append(seg_text)
        except Exception as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"faster-whisper transcription failed: {exc}",
                cause=exc,
            ) from exc

        return {"text": " ".join(t for t in texts if t).strip(), "segments": segments}
