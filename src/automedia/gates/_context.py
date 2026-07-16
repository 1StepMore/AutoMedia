"""Typed ``GateContext`` dataclass — replaces ``dict[str, Any]`` for gate context.

Every gate receives a ``GateContext`` instance.  The class provides
typed attributes for all commonly-used context keys while remaining
**dict-compatible** via ``get()``, ``__getitem__``, ``__setitem__``,
``__contains__``, and ``setdefault()`` so that:

* Existing test fixtures that pass plain ``dict`` objects to
  ``gate.execute(ctx)`` continue to work unchanged (Python does not
  enforce type hints at runtime).
* Helper functions that accept ``context: dict[str, Any]`` and call
  ``.get()`` work transparently.
* Hooks receive a plain ``dict`` via ``to_dict()`` for full backward
  compatibility.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar

from structlog import get_logger

log = get_logger(__name__)


@dataclass
class GateContext:
    """Typed pipeline context with dict-compatible access.

    Core fields are typed dataclass attributes.  Gate-specific fields
    that are only used by one or two gates live in the ``extra`` dict.

    The class implements the ``get`` / ``__getitem__`` / ``__setitem__``
    / ``__contains__`` / ``setdefault`` protocol so that it can be used
    interchangeably with a plain ``dict[str, Any]``.
    """

    # ------------------------------------------------------------------
    # Core fields (set by runner / engine)
    # ------------------------------------------------------------------

    topic: str = ""
    brand: str = ""
    project_id: str = ""
    project_dir: str = ""
    correlation_id: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"
    lang_config: dict[str, Any] = field(default_factory=dict)
    mode: str = "auto"
    force_provenance: bool = False

    # Set per-gate by the engine loop
    gate_name: str = ""

    # ------------------------------------------------------------------
    # Content fields (set by CW, read by G0-G5, G4, etc.)
    # ------------------------------------------------------------------

    content: str = ""
    draft: str | None = None
    source_data: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    brand_profile: dict[str, Any] | None = None
    video_script: str | None = None
    title: str = ""
    digest: str = ""
    cover_image: str = ""
    body_images: list[str] = field(default_factory=list)

    # V3 — content semantic
    source_keywords: list[str] = field(default_factory=list)
    content_keywords: list[str] = field(default_factory=list)
    source_texts: list[str] = field(default_factory=list)

    # V0 — lint
    lint_result: dict[str, Any] = field(default_factory=dict)

    # V2 — pre-send whisper / audio
    transcription: str = ""
    audio_path: str = ""
    expected_md5: str = ""
    full_audio: bool = True

    # V5 — mp3 vs srt
    whisper_text: str = ""
    srt_text: str = ""

    # L1 — publish log
    publish_log: dict[str, Any] = field(default_factory=dict)

    # V7 — six-step hard
    required_files: list[str] = field(default_factory=list)
    file_sizes: dict[str, int] = field(default_factory=dict)
    md5_records: dict[str, dict[str, str]] = field(default_factory=dict)
    whisper_full_audio: bool = True
    actual_format: str = ""
    expected_format: str = ""
    actual_duration: float = 0.0
    expected_duration_min: float = 0.0
    expected_duration_max: float = 0.0

    # V6 — subtitle render
    avg_brightness: int = 0
    contrast: int = 0
    opacity: float = 0.0
    pixel_valid: bool = False

    # V4 — TTS brand asset
    voice_id: str = ""
    expected_voice_id: str = ""
    speaking_rate: float = 0.0
    segments: list[dict[str, Any]] = field(default_factory=list)

    # V1 — vision QA
    entries: list[dict[str, Any]] = field(default_factory=list)

    # L2 — archive validation
    archive_status: str = ""
    force: bool = False
    archive_path: str = ""
    archive_metadata: dict[str, Any] = field(default_factory=dict)
    archive_version: str = ""
    output_dir: str = ""

    # L4 — translation quality
    translation_result: dict[str, Any] | None = None  # OL pipeline returns dict
    source_lang: str = ""
    target_lang: str = ""

    # L3 — platform integrity
    platforms: list[str] = field(default_factory=list)
    expected_platforms: list[str] = field(default_factory=list)
    content_platform_map: dict[str, Any] = field(default_factory=dict)
    unified_content: str = ""
    media_files: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    platform_variants: dict[str, str] = field(default_factory=dict)
    formats: list[str] = field(default_factory=list)
    required_formats: list[str] = field(default_factory=list)

    # Output (mutated by gates, e.g. CW appends to output_files)
    output_files: list[dict[str, Any]] = field(default_factory=list)

    # Test / mock (used by all gates for deterministic testing)
    mock_results: dict[str, dict[str, Any]] | None = None

    # Source material (set by runner when source_path/source_url provided)
    source_content: str = ""
    source_material: dict[str, Any] = field(default_factory=dict)

    # Catch-all for any unmapped keys
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Key alias mapping (legacy dict key → dataclass field name)
    # ------------------------------------------------------------------

    _KEY_ALIASES: ClassVar[dict[str, str]] = {
        "_gate_name": "gate_name",
        "_mock_results": "mock_results",
    }

    # ------------------------------------------------------------------
    # Dict-compatible protocol
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve(key: str) -> str:
        """Resolve aliased keys (e.g. ``_gate_name`` → ``gate_name``)."""
        return GateContext._KEY_ALIASES.get(key, key)

    def _is_field(self, key: str) -> bool:
        """Return ``True`` if *key* is a declared dataclass field."""
        return key in type(self).__dataclass_fields__

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401 — dict-compat
        key = self._resolve(key)
        if self._is_field(key):
            return getattr(self, key)
        return self.extra[key]

    def __setitem__(self, key: str, value: Any) -> None:  # noqa: ANN401 — dict-compat
        key = self._resolve(key)
        if self._is_field(key):
            object.__setattr__(self, key, value)
        else:
            self.extra[key] = value

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401 — dict-compat
        """Dict-compatible ``.get()`` with default."""
        key = self._resolve(key)
        if self._is_field(key):
            return getattr(self, key)
        return self.extra.get(key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:  # noqa: ANN401 — dict-compat
        """Dict-compatible ``.setdefault()``."""
        key = self._resolve(key)
        if self._is_field(key):
            return getattr(self, key)
        return self.extra.setdefault(key, default)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        key = self._resolve(key)
        if self._is_field(key):
            return True
        return key in self.extra

    def keys(self) -> list[str]:
        """Return all keys (field names + extra keys)."""
        result = [f.name for f in fields(self) if f.name != "extra"]
        result.extend(self.extra.keys())
        return result

    def values(self) -> list[Any]:
        """Return all values."""
        result = [getattr(self, f.name) for f in fields(self) if f.name != "extra"]
        result.extend(self.extra.values())
        return result

    def items(self) -> list[tuple[str, Any]]:
        """Return all key-value pairs."""
        result = [(f.name, getattr(self, f.name)) for f in fields(self) if f.name != "extra"]
        result.extend(self.extra.items())
        return result

    def __iter__(self) -> Iterator[str]:
        """Iterate over keys (for dict.update() compatibility)."""
        return iter(self.keys())

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain ``dict`` for hook / serialization compat."""
        result: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "extra":
                result.update(self.extra)
            else:
                result[f.name] = getattr(self, f.name)
        # Preserve legacy key names for hooks that expect them
        result["_gate_name"] = self.gate_name
        result["_mock_results"] = self.mock_results
        return result
