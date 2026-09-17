"""DetectorRegistry — singleton registry for AI-writing-taste detectors.

Mirrors the GateRegistry pattern (``automedia.gates.base``): a per-package
singleton built on :class:`BaseRegistry` that auto-registers every concrete
:class:`BaseDetector` subclass under its ``_detector_name``.

Unlike GateRegistry, there is no RL6-style name-format check (detector
names are free-form snake_case) and no hard failure for missing
environment configuration.  Registration is unconditional; availability
is a runtime property of each detector via ``available()``.
"""

from __future__ import annotations

import os
import warnings
from typing import TYPE_CHECKING

from automedia.core.registry import BaseRegistry

if TYPE_CHECKING:
    from automedia.detectors.base import BaseDetector


class DetectorRegistry(BaseRegistry):
    """Singleton registry that auto-registers BaseDetector subclasses by name.

    Inherits singleton lifecycle and CRUD from :class:`BaseRegistry`.
    Overrides :meth:`_validate` to reject duplicate registrations and to
    warn (never hard-fail) when a detector's required env var is unset.
    """

    # ------------------------------------------------------------------
    # Validation hook
    # ------------------------------------------------------------------

    def _validate(self, key: str, value: type[BaseDetector]) -> None:
        """Reject duplicates; warn when ``_env_required`` is unset in the env.

        A detector whose required env var is missing is STILL registered —
        the warning is advisory only (mirrors the RL7 soft warning in
        GateRegistry).  Availability is decided at runtime by
        ``BaseDetector.available()``, not at registration time.
        """
        if key in self._registry:
            raise KeyError(f"Detector '{key}' is already registered by {self._registry[key]}")

        env_required: str = value._env_required
        if env_required and not os.environ.get(env_required):
            warnings.warn(
                f"Detector '{key}' requires env var '{env_required}' which is "
                f"unset; it registers anyway but available() will report False "
                f"until the variable is provided.",
                stacklevel=2,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, detector_cls: type[BaseDetector]) -> None:  # type: ignore[override]  # narrower signature than BaseRegistry.register(key, value)
        """Register a BaseDetector subclass under its ``_detector_name``.

        Validates the name (duplicate rejection) and warns when the
        detector's env requirement is unmet, then stores the class.
        """
        super().register(detector_cls._detector_name, detector_cls)

    def get(self, detector_name: str) -> type[BaseDetector]:
        """Look up a detector class by name.

        Raises :class:`KeyError` (with the available names) if *detector_name*
        is not registered.
        """
        if detector_name not in self._registry:
            raise KeyError(
                f"Detector '{detector_name}' is not registered. Available: {list(self._registry)}"
            )
        return self._registry[detector_name]

    def get_all(self) -> dict[str, type[BaseDetector]]:
        """Return a copy of the full name→class mapping."""
        return dict(self._registry)

    def __repr__(self) -> str:
        return f"DetectorRegistry({len(self)} detectors: {', '.join(self.list())})"
