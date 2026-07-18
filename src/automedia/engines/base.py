"""Abstract base engine — ABC + 4 modal ABCs with auto-registration.

Every concrete engine subclass of :class:`BaseEngine` is automatically
registered in the global :class:`EngineRegistry` singleton via
``__init_subclass__``, mirroring the pattern used by :class:`BaseGate`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class BaseEngine(ABC):
    """Abstract base for every engine in the engine abstraction layer.

    Every concrete subclass **must** define:
    - ``engine_name`` as a class-level string (e.g. ``"edge-tts"``)
    - ``modality`` as a class-level string (e.g. ``"tts"``)
    - :meth:`check_available` returning a ``(bool, str)`` tuple

    Subclasses are automatically registered in the module-level
    ``_engine_registry`` singleton via ``__init_subclass__``.
    """

    # Declared here so mypy knows subclasses define these; no default value
    # so hasattr() in __init_subclass__ still works correctly.
    engine_name: ClassVar[str]
    modality: ClassVar[str]

    def __init__(self, engine_config: dict[str, Any] | None = None) -> None:
        """Initialise the engine with an optional configuration dict.

        Args:
            engine_config: Optional engine-level configuration dictionary.
                Stored as ``self._config``.
        """
        self._config: dict[str, Any] = engine_config or {}

    # -- Required methods ---------------------------------------------------

    @abstractmethod
    def check_available(self) -> tuple[bool, str]:
        """Verify that all external dependencies for this engine are ready.

        Returns:
            A tuple of ``(available, message)`` where ``available`` is
            ``True`` if the engine can be used, and ``message`` provides
            diagnostic details on failure.
        """
        ...

    # -- Optional overrides ------------------------------------------------

    def validate_config(self) -> None:
        """Validate the engine's configuration for completeness.

        Override in subclasses that require specific config keys.
        Raises :class:`ValueError` on invalid configuration.
        """
        return None

    # -- Automatic registration --------------------------------------------

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401 — pass-through to super().__init_subclass__
        """Auto-register concrete subclasses in the global engine registry."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "engine_name") and hasattr(cls, "modality"):
            from automedia.engines.registry import _engine_registry

            _engine_registry.register(cls.engine_name, cls, modality=cls.modality)

    # -- String representations -------------------------------------------

    def __str__(self) -> str:
        return f"{self.engine_name}"

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} engine_name={self.engine_name!r} modality={self.modality!r}>"
        )


class BaseTTSEngine(BaseEngine, ABC):
    """Text-to-Speech engine base.

    Concrete subclasses (e.g. ``EdgeTTSEngine``) must implement
    :meth:`synthesize` to convert text to a spoken audio file.
    """

    @abstractmethod
    def synthesize(self, text: str, voice: str, output_path: str) -> str:
        """Convert *text* to speech and write the audio to *output_path*.

        Args:
            text: The text content to synthesize.
            voice: The voice identifier (e.g. ``"zh-CN-XiaoxiaoNeural"``).
            output_path: Absolute or relative path for the generated audio file.

        Returns:
            The absolute path to the generated audio file (may differ from
            *output_path* if the engine appends a file extension).
        """
        ...


class BaseASREngine(BaseEngine, ABC):
    """Automatic Speech Recognition engine base.

    Concrete subclasses (e.g. ``WhisperASREngine``) must implement
    :meth:`transcribe` to convert audio to text segments.
    """

    @abstractmethod
    def transcribe(self, audio_path: str, language: str) -> dict[str, Any]:
        """Transcribe *audio_path* into text segments.

        Args:
            audio_path: Path to the audio file to transcribe.
            language: Source language code (e.g. ``"zh"``, ``"en"``).

        Returns:
            A dictionary containing transcription results. The expected
            structure includes at minimum:
            - ``text`` (str): Full transcribed text.
            - ``segments`` (list[dict]): Per-segment timing with
              ``start``, ``end``, and ``text`` keys.
        """
        ...


class BaseImageEngine(BaseEngine, ABC):
    """Image generation engine base.

    Concrete subclasses (e.g. ``ComfyUIImageEngine``) must implement
    :meth:`generate` to produce an image from a text prompt.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        output_path: str,
    ) -> str:
        """Generate an image from *prompt* and write it to *output_path*.

        Args:
            prompt: The text prompt describing the desired image.
            width: Desired image width in pixels.
            height: Desired image height in pixels.
            output_path: Path where the generated image should be saved.

        Returns:
            The absolute path to the generated image file.
        """
        ...


class BaseVideoEngine(BaseEngine, ABC):
    """Video rendering engine base.

    Concrete subclasses (e.g. ``HyperFramesVideoEngine``) must implement
    :meth:`render` to assemble a video from the provided assets.

    **Assets schema**
    The ``assets`` dict passed to :meth:`render` is expected to contain:

    .. code-block:: python

        {
            "images": list[str],      # Paths to image files for video frames
            "audio": str,             # Path to the audio track file
            "subtitles": str,         # Path to the subtitle file (SRT or ASS)
            "template_dir": str,      # Path to the video template directory
            "content": str,           # The rendered text content for overlays
        }
    """

    @abstractmethod
    def render(self, assets: dict[str, Any], output_path: str) -> str:
        """Render a video from *assets* and write it to *output_path*.

        Args:
            assets: A dictionary of asset paths and metadata. See the
                class docstring for the expected schema.
            output_path: Path where the rendered video should be saved.

        Returns:
            The absolute path to the rendered video file.
        """
        ...
