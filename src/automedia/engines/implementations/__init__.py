"""Concrete engine implementations for all supported modalities.

Each module in this package defines one or more :class:`BaseEngine` subclasses
that register themselves via ``__init_subclass__`` when imported.

Import each implementation module here to trigger auto-registration in the
global :class:`~automedia.engines.registry.EngineRegistry` singleton.
"""

from automedia.engines.implementations import (
    asr_faster_whisper,  # noqa: F401
    asr_whisper,  # noqa: F401
    image_comfyui,  # noqa: F401
    image_local,  # noqa: F401
    tts_edge,  # noqa: F401
    tts_piper,  # noqa: F401
    video_hyperframes,  # noqa: F401
)
