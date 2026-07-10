"""Property-based tests for gate utilities using Hypothesis."""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from automedia.core.config_loader import deep_merge
from automedia.gates._result import build_gate_result

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A single gate check dict: must have name, passed, detail
_gate_check = st.fixed_dictionaries(
    {
        "name": st.text(min_size=1, max_size=50),
        "passed": st.booleans(),
        "detail": st.text(max_size=200),
    }
)


def _gate_checks(min_size: int = 0, max_size: int = 20) -> st.SearchStrategy[list[dict[str, Any]]]:
    """Strategy for a list of gate check dicts."""
    return st.lists(_gate_check, min_size=min_size, max_size=max_size)


# Nested dicts for deep_merge testing (scalars + one level of nesting)
_flat_dict = st.dictionaries(
    keys=st.text(min_size=1, max_size=10),
    values=st.one_of(st.integers(), st.text(max_size=20), st.booleans()),
    max_size=8,
)

_nested_dict = st.dictionaries(
    keys=st.text(min_size=1, max_size=10),
    values=st.one_of(
        st.integers(),
        st.text(max_size=20),
        st.booleans(),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10),
            values=st.one_of(st.integers(), st.text(max_size=20)),
            max_size=5,
        ),
    ),
    max_size=8,
)

# Gate name strategy — alphanumeric strings of length 1-20
_gate_name = st.from_regex(r"[A-Za-z0-9_-]+", fullmatch=True)


# ---------------------------------------------------------------------------
# build_gate_result property tests
# ---------------------------------------------------------------------------


@given(checks=_gate_checks(min_size=1), gate=_gate_name)
def test_build_result_always_has_required_keys(checks: list[dict[str, Any]], gate: str) -> None:
    """build_gate_result always returns a dict with the four required keys."""
    result = build_gate_result(checks, gate=gate)
    assert "passed" in result
    assert "checks" in result
    assert "gate" in result
    assert "expected_vs_actual" in result


@given(checks=_gate_checks(min_size=1), gate=_gate_name)
def test_all_passed_iff_all_checks_pass(checks: list[dict[str, Any]], gate: str) -> None:
    """result["passed"] is True exactly when every individual check passed."""
    result = build_gate_result(checks, gate=gate)
    expected = all(c["passed"] for c in checks)
    assert result["passed"] is expected


@given(checks=_gate_checks(min_size=1), gate=_gate_name)
def test_first_fail_appears_in_expected_vs_actual(checks: list[dict[str, Any]], gate: str) -> None:
    """When any check fails, expected_vs_actual references the first failing check."""
    result = build_gate_result(checks, gate=gate)
    failures = [c for c in checks if not c["passed"]]
    if failures:
        assert result["expected_vs_actual"]["check"] == failures[0]["name"]
        assert result["expected_vs_actual"]["actual"] == failures[0].get("detail", "")
    else:
        # All passed — expected_vs_actual points to the first check
        assert result["expected_vs_actual"]["check"] == checks[0]["name"]


@given(gate=_gate_name, checks=st.just([]))
def test_empty_checks_do_not_crash(checks: list[dict[str, Any]], gate: str) -> None:
    """An empty checks list produces a valid result without raising."""
    result = build_gate_result(checks, gate=gate)
    assert result["passed"] is True  # vacuously true
    assert result["checks"] == []
    assert result["gate"] == gate
    assert result["expected_vs_actual"] == {}


@given(checks=_gate_checks(min_size=1), gate=_gate_name, error=st.text(max_size=100))
def test_error_and_extra_passthrough(
    checks: list[dict[str, Any]], gate: str, error: str
) -> None:
    """The error field and **extra kwargs are passed through verbatim."""
    result = build_gate_result(checks, gate=gate, error=error, confidence=0.42)
    assert result["error"] == error
    assert result["confidence"] == 0.42


# ---------------------------------------------------------------------------
# deep_merge property tests
# ---------------------------------------------------------------------------


@given(base=_nested_dict, override=_nested_dict)
@settings(max_examples=200)
def test_deep_merge_neither_mutates(base: dict[str, Any], override: dict[str, Any]) -> None:
    """deep_merge must not mutate either input dict."""
    base_orig = {k: _deep_copy_shallow(v) for k, v in base.items()}
    override_orig = {k: _deep_copy_shallow(v) for k, v in override.items()}

    deep_merge(base, override)

    assert base == base_orig, "base was mutated"
    assert override == override_orig, "override was mutated"


@given(base=_nested_dict, override=_nested_dict)
@settings(max_examples=200)
def test_deep_merge_override_keys_take_priority(
    base: dict[str, Any], override: dict[str, Any]
) -> None:
    """For non-dict values, override values replace base values."""
    result = deep_merge(base, override)
    for key, value in override.items():
        if key not in base or not (isinstance(base[key], dict) and isinstance(value, dict)):
            assert result[key] == value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_copy_shallow(obj: object) -> object:
    """Lightweight copy for nested dicts (one level deep)."""
    if isinstance(obj, dict):
        return dict(obj)
    return obj
