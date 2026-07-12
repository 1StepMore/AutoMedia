"""
5 Cruel Acceptance Test Scenarios

Each scenario exercises a production failure mode that mock-based tests
cannot catch.  These tests use real APIs (or realistic mocks at the
library level for determinism).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [
    pytest.mark.cruel,
    pytest.mark.e2e,
    pytest.mark.slow,
]


# =============================================================================
# Scenario A: Missing API Key → Clear Error
# =============================================================================


@pytest.mark.skipif(not os.environ.get("AUTOMEDIA_LLM_API_KEY"), reason="requires API key")
def test_cruel_a_missing_api_key_clear_error() -> None:
    """Missing API key must produce a clear, actionable error message."""
    from automedia.core.llm_client import llm_complete, LLMError

    with patch.dict(os.environ, clear=True), \
         patch("automedia.core.config_loader.load_config", return_value={"llm": {"text_generation": {"model": "test-model"}}}):
        try:
            llm_complete("Say hello")
            pytest.fail("Expected LLMError for missing API key")
        except LLMError as e:
            msg = str(e).lower()
            assert "api" in msg or "key" in msg, (
                f"Error must mention API key configuration, got: {e}"
            )


# =============================================================================
# Scenario B: Invalid API Key → Clear Error
# =============================================================================


@pytest.mark.skipif(not os.environ.get("AUTOMEDIA_LLM_API_KEY"), reason="requires API key")
def test_cruel_b_invalid_api_key_clear_error() -> None:
    """Invalid API key must produce a clear authentication error."""
    from automedia.core.llm_client import llm_complete, LLMError

    with patch.dict(os.environ, {"AUTOMEDIA_LLM_API_KEY": "sk-invalid-key-for-test"}):
        try:
            llm_complete("Say hello")
            pytest.fail("Expected LLMError for invalid API key")
        except LLMError as e:
            msg = str(e).lower()
            assert any(term in msg for term in ["auth", "401", "unauthorized", "key", "forbidden"]), (
                f"Error must indicate auth failure, got: {e}"
            )


# =============================================================================
# Scenario C: MD5 Corruption Detection During Resume
# =============================================================================


@pytest.mark.skipif(not os.environ.get("AUTOMEDIA_LLM_API_KEY"), reason="requires API key")
def test_cruel_c_md5_detects_tampered_asset_during_resume(tmp_path: str) -> None:
    """_verify_resume_integrity detects file tampering using REAL MD5 functions.

    Uses real ``record_md5`` / ``verify_md5`` against a synthetic project
    directory (no real LLM calls), then runs the runner's
    ``_verify_resume_integrity`` to confirm the full integration path.
    """
    from automedia.hooks.md5_tracker import record_md5
    from automedia.pipelines.runner import _verify_resume_integrity

    proj = Path(str(tmp_path))

    # Create synthetic gate outputs and record MD5s
    gate_order = ["CW", "G0", "G1", "G2", "G3", "G4", "G5"]
    files: list[tuple[str, Path]] = []
    for name in gate_order:
        f = proj / f"{name}_output.txt"
        f.write_text(f"Content from gate {name}")
        record_md5(str(proj), name, str(f))
        files.append((name, f))

    # Tamper with the G0 output
    files[2][1].write_text("TAMPERED CONTENT — original checksum will not match")

    # Run _verify_resume_integrity as the runner does and capture the warning
    from structlog.testing import capture_logs
    with capture_logs() as cap:
        _verify_resume_integrity(
            project_dir=str(proj),
            resume_from="G1",
            gate_names_in_mode=gate_order,
        )

    mismatch_events = [
        e for e in cap
        if "md5" in str(e).lower() and ("mismatch" in str(e).lower() or "fail" in str(e).lower())
    ]
    assert mismatch_events, (
        "No MD5 mismatch warning logged for tampered gate G0"
    )


# =============================================================================
# Scenario D: Doctor Detects Missing LLM Connectivity
# =============================================================================


@pytest.mark.skipif(not os.environ.get("AUTOMEDIA_LLM_API_KEY"), reason="requires API key")
def test_cruel_d_doctor_detects_llm_connectivity() -> None:
    """Doctor must report LLM API connectivity status."""
    from automedia.core.doctor import Doctor

    d = Doctor()
    results = d.check_dependencies()
    names = [r["name"] for r in results]
    assert "llm_api" in names, "Doctor must include llm_api check"

    llm_result = next(r for r in results if r["name"] == "llm_api")
    assert llm_result["installed"] is True, (
        f"LLM check failed with valid config: {llm_result.get('version')}"
    )
    assert llm_result["version"] == "API reachable"
    assert llm_result["path"] is None


# =============================================================================
# Scenario E: MCP Allowlist Blocks Non-Allowed Paths with Clear Error
# =============================================================================


def test_cruel_e_mcp_allowlist_clear_error() -> None:
    """MCP allowlist must produce a clear error for blocked paths."""
    from automedia.mcp.allowlist import _require_allowed, _reset_allowlist_cache

    _reset_allowlist_cache()

    with pytest.raises(ValueError) as excinfo:
        _require_allowed("/etc/passwd")

    msg = str(excinfo.value)
    assert "/etc/passwd" in msg, "Error must mention the blocked path"
    assert "allowlist" in msg.lower(), "Error must mention mcp_allowlist.yaml"
