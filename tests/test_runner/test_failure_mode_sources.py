"""Failure modes have one machine-readable source (issue #279)."""

from __future__ import annotations

import automedia.gates  # noqa: F401 — ensure every gate is registered
from automedia.gates.base import _registry
from automedia.gates.failure_modes import FAILURE_MODES
from automedia.pipelines.dag import AUTO_GATE_DAG


def test_every_knowledge_entry_has_a_failure_mode() -> None:
    missing = sorted(name for name, entry in FAILURE_MODES.items() if "failure_mode" not in entry)
    assert not missing, missing


def test_knowledge_failure_mode_matches_the_registered_gate() -> None:
    mismatches = {
        name: (FAILURE_MODES[name]["failure_mode"], _registry.get(name)._failure_mode)
        for name in FAILURE_MODES
        if FAILURE_MODES[name]["failure_mode"] != _registry.get(name)._failure_mode
    }
    assert not mismatches, mismatches


def test_dag_failure_mode_matches_the_knowledge_base() -> None:
    mismatches = {
        name: (node.failure_mode, FAILURE_MODES[name]["failure_mode"])
        for name, node in AUTO_GATE_DAG.items()
        if node.failure_mode != FAILURE_MODES[name]["failure_mode"]
    }
    assert not mismatches, mismatches


def test_registry_and_knowledge_cover_the_same_gates() -> None:
    production = {
        name
        for name, gate_cls in _registry.get_all().items()
        if gate_cls.__module__.startswith("automedia.gates")
    }
    assert production == set(FAILURE_MODES)
