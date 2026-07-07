"""Tests for automedia.gates.failure_modes — FAILURE_MODES knowledge base."""

from __future__ import annotations

import pytest

from automedia.gates.failure_modes import FAILURE_MODES

# Known gate names (matches the keys in failure_modes.py)
_GATE_NAMES = [
    "G0", "G1", "G2", "G3", "G4", "G5",
    "V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "L1", "L2", "L3",
    "pre-gate",
]

_REQUIRED_KEYS = {"description", "common_causes", "fixes", "docstring_ref"}


# ===================================================================
# Tests
# ===================================================================


class TestFailureModesStructure:
    """FAILURE_MODES dict structure and completeness."""

    def test_all_gates_present(self):
        """Every known gate name is a key in FAILURE_MODES."""
        for name in _GATE_NAMES:
            assert name in FAILURE_MODES, f"Missing failure mode entry for gate '{name}'"

    def test_no_unexpected_gates(self):
        """FAILURE_MODES has no keys that aren't in the known list."""
        for key in FAILURE_MODES:
            assert key in _GATE_NAMES, f"Unexpected gate '{key}' in FAILURE_MODES"

    def test_every_entry_has_required_keys(self):
        """Each entry contains description, common_causes, fixes, docstring_ref."""
        for gate_name, entry in FAILURE_MODES.items():
            missing = _REQUIRED_KEYS - set(entry.keys())
            assert not missing, f"Gate '{gate_name}' is missing keys: {missing}"

    def test_common_causes_is_nonempty_list(self):
        """Every gate has at least one common cause."""
        for gate_name, entry in FAILURE_MODES.items():
            causes = entry.get("common_causes", [])
            assert isinstance(causes, list), f"Gate '{gate_name}' common_causes is not a list"
            assert len(causes) > 0, f"Gate '{gate_name}' has no common causes"

    def test_fixes_is_nonempty_list(self):
        """Every gate has at least one fix."""
        for gate_name, entry in FAILURE_MODES.items():
            fixes = entry.get("fixes", [])
            assert isinstance(fixes, list), f"Gate '{gate_name}' fixes is not a list"
            assert len(fixes) > 0, f"Gate '{gate_name}' has no fixes"

    def test_docstring_ref_is_string(self):
        """docstring_ref is a string for every gate."""
        for gate_name, entry in FAILURE_MODES.items():
            ref = entry.get("docstring_ref", "")
            assert isinstance(ref, str), f"Gate '{gate_name}' docstring_ref is not a string"
            assert ref, f"Gate '{gate_name}' docstring_ref is empty"


class TestFailureModesContent:
    """Specific content correctness."""

    def test_g0_has_correct_description(self):
        """G0 description mentions fact-check."""
        desc = FAILURE_MODES["G0"]["description"]
        assert isinstance(desc, str)
        assert "fact" in desc.lower() or "Fact" in desc

    def test_g3_mentions_brand_name(self):
        """G3 description mentions 壹目贯维 brand."""
        desc = FAILURE_MODES["G3"]["description"]
        assert isinstance(desc, str)
        assert "brand" in desc.lower() or "CTA" in desc

    def test_pre_gate_exists(self):
        """pre-gate entry describes topic selection."""
        entry = FAILURE_MODES["pre-gate"]
        desc = entry["description"]
        assert isinstance(desc, str)
        assert "topic" in desc.lower()

    def test_g0_fixes_reference_source_data(self):
        """G0 fixes mention source_data."""
        fixes = FAILURE_MODES["G0"]["fixes"]
        all_text = " ".join(str(f) for f in fixes).lower()
        assert "source" in all_text

    def test_v6_mentions_subtitle_rendering(self):
        """V6 description mentions subtitle or render."""
        desc = FAILURE_MODES["V6"]["description"]
        assert isinstance(desc, str)
        assert "subtitle" in desc.lower() or "render" in desc.lower()
