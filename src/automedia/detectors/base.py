"""Base detector abstraction for the AI-writing-taste detector framework.

A detector inspects a piece of text and reports how AI-written it reads,
as a normalized ``ai_score`` in [0, 1] (higher = more AI-written).  The
framework is pluggable: any :class:`BaseDetector` subclass is
automatically registered in the :class:`DetectorRegistry` singleton via
``__init_subclass__`` — the same pattern BaseGate uses for gates.

Environment gating: a detector declares the env var it needs via the
class attribute ``_env_required`` (empty string = no env needed, always
available).  Registration is UNCONDITIONAL — a detector whose env var is
missing is still registered; :meth:`BaseDetector.available` reports False
until the variable is provided.  This keeps registration a static,
import-time concern and availability a runtime question.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, ClassVar, NotRequired, TypedDict

from automedia.detectors.registry import DetectorRegistry
from automedia.gates._result import CheckResult


class DetectorResult(TypedDict):
    """Structured result produced by a detector's ``detect`` call.

    ``name``, ``ai_score``, ``passed``, and ``detail`` are always present.
    Optional keys:

    - ``checks``: per-check breakdown (each entry has ``name``, ``passed``,
      and ``detail``) — mirrors the gate ``CheckResult`` shape.
    - ``method``: how the score was produced (e.g. ``"deterministic"``)
      so consumers can tell real evidence from provenance.
    """

    name: str
    ai_score: float
    passed: bool
    detail: str
    checks: NotRequired[list[CheckResult]]
    method: NotRequired[str]


# Module-level singleton — used by __init_subclass__
_registry: DetectorRegistry = DetectorRegistry()


class BaseDetector(ABC):
    """Abstract base for every AI-writing-taste detector.

    Every concrete subclass **must** define:

    - ``_detector_name`` as a class-level string (e.g. ``"deterministic_taste"``)
    - ``detect(self, text: str) -> DetectorResult``

    ``_env_required`` is optional; the empty string (the default) means
    the detector needs no environment configuration and is always
    available.  Subclasses are automatically registered in the module-level
    ``_registry`` singleton via ``__init_subclass__`` — registration is
    unconditional and never blocked by a missing env var.
    """

    # Declared here so mypy knows subclasses define these; no default value
    # for _detector_name so hasattr() in __init_subclass__ still works.
    _detector_name: ClassVar[str]
    _env_required: ClassVar[str] = ""

    @property
    def detector_name(self) -> str:
        """Short identifier for this detector (e.g. ``"deterministic_taste"``)."""
        try:
            return self._detector_name
        except AttributeError as err:
            raise NotImplementedError(
                f"{type(self).__name__} must define class-level '_detector_name'"
            ) from err

    @detector_name.setter
    def detector_name(self, _value: str) -> None:
        raise AttributeError("detector_name is read-only")

    @property
    def env_required(self) -> str:
        """Name of the env var that gates this detector (``""`` = always available)."""
        return self._env_required

    @env_required.setter
    def env_required(self, _value: str) -> None:
        raise AttributeError("env_required is read-only")

    # -- Availability ----------------------------------------------------

    def available(self) -> bool:
        """Whether this detector can run in the current environment.

        True when ``_env_required`` is empty, or when the required env var
        is set and non-empty.  Detectors that are not available should be
        skipped by callers (e.g. :func:`automedia.detectors.detect_text`).
        """
        if not self._env_required:
            return True
        return bool(os.environ.get(self._env_required))

    # -- Required method -------------------------------------------------

    @abstractmethod
    def detect(self, text: str) -> DetectorResult:
        """Detect AI-writing taste in *text* and return a :class:`DetectorResult`.

        Args:
            text: The text to inspect.  Implementations must handle empty
                and whitespace-only input gracefully (score 0.0, passed).

        Returns:
            A :class:`DetectorResult` with a normalized ``ai_score`` in
            [0, 1], ``passed``, a human-readable ``detail``, and optional
            ``checks``/``method`` keys.  Implementations must never
            fabricate evidence: an unavailable detector raises instead of
            returning a score.
        """
        ...

    # -- Automatic registration -------------------------------------------

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401 — pass-through to super().__init_subclass__
        """Auto-register concrete subclasses in the global registry.

        Registration is unconditional: a detector whose required env var is
        missing is still registered (its ``available()`` reports False).
        """
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_detector_name"):
            _registry.register(cls)

    # -- String representations -------------------------------------------

    def __str__(self) -> str:
        return self.detector_name

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} detector_name={self.detector_name!r}"
            f" env_required={self.env_required!r}>"
        )
