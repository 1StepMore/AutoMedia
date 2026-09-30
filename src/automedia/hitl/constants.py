"""Canonical HITL constants shared by the ``hitl``, ``gates``, and ``pipelines`` layers.

This module is a deliberate zero-import leaf: it must not import anything from
``automedia`` so that ``gates`` and ``pipelines`` can depend on it without
risking an import cycle.  ``HITL_DEFAULT_TIMEOUT_S`` is the single Python owner
of the default H0 human-review pause budget; the YAML config default in
``manifests/defaults.yaml`` (``gate_engine.hitl_timeout_s``) restates the same
number because YAML cannot import Python, and a drift test pins the two together.
"""

from __future__ import annotations

HITL_DEFAULT_TIMEOUT_S: int = 3600
"""Default H0 human-review pause budget, in seconds (one hour)."""
