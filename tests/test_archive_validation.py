"""Tests for L2ArchiveValidation gate — archive strong validation.

Red Line 8: Rejects archives whose status is not "published" unless --force.
"""

from __future__ import annotations

from typing import Any

from automedia.gates.archive_validation import _CHECK_NAMES, L2ArchiveValidation
from automedia.gates.base import BaseGate, _registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    *,
    archive_status: str = "published",
    force: bool = False,
    archive_path: str = "/data/archives/test-archive",
    archive_metadata: dict[str, Any] | None = None,
    archive_version: str = "1.0.0",
    output_dir: str = "/data/output/test",
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {
        "archive_status": archive_status,
        "force": force,
        "archive_path": archive_path,
        "archive_metadata": archive_metadata
        if archive_metadata is not None
        else {
            "title": "Test Archive",
            "platform": "wechat",
            "created_at": "2026-07-07T10:00:00",
        },
        "archive_version": archive_version,
        "output_dir": output_dir,
    }
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    """Return mock results where every check passes."""
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "failed") -> dict[str, dict[str, Any]]:
    """Return mock results where *name* fails and the rest pass."""
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestL2Metadata:
    """L2ArchiveValidation has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = L2ArchiveValidation()
        assert gate.gate_name == "L2"

    def test_failure_mode(self) -> None:
        gate = L2ArchiveValidation()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(L2ArchiveValidation, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "L2" in _registry
        assert _registry.get("L2") is L2ArchiveValidation


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestL2MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All 6 mock checks pass → overall passed=True."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "L2"
        assert result["error"] is None
        assert len(result["checks"]) == 6

    def test_archive_status_failure_detected(self) -> None:
        """archive_status failure → overall passed=False (without force)."""
        ctx = _make_context(
            archive_status="draft",
            mock_results=_fail_check("archive_status", "not published"),
        )
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert any(c["name"] == "archive_status" for c in failed)

    def test_all_checks_fail(self) -> None:
        """All 6 checks fail → overall passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is False
        assert all(not c["passed"] for c in result["checks"])


# =========================================================================
# Real-logic tests (Red Line 8)
# =========================================================================


class TestL2RedLine8:
    """Red Line 8: archive must be published or --force must be set."""

    def test_published_archive_passes(self) -> None:
        """archive_status='published' → passes."""
        ctx = _make_context(archive_status="published", force=False)
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is True
        status_check = next(c for c in result["checks"] if c["name"] == "archive_status")
        assert status_check["passed"] is True

    def test_draft_archive_fails_without_force(self) -> None:
        """archive_status='draft' without force → fails Red Line 8."""
        ctx = _make_context(archive_status="draft", force=False)
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is False
        status_check = next(c for c in result["checks"] if c["name"] == "archive_status")
        assert status_check["passed"] is False

    def test_draft_archive_passes_with_force(self) -> None:
        """archive_status='draft' with force=True → passes (Red Line 8 override)."""
        ctx = _make_context(archive_status="draft", force=True)
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is True
        status_check = next(c for c in result["checks"] if c["name"] == "archive_status")
        assert status_check["passed"] is True  # Overridden by force
        assert "overridden by --force" in status_check["detail"]

    def test_archived_status_fails_without_force(self) -> None:
        """archive_status='archived' without force → fails."""
        ctx = _make_context(archive_status="archived", force=False)
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is False

    def test_archived_status_passes_with_force(self) -> None:
        """archive_status='archived' with force=True → passes."""
        ctx = _make_context(archive_status="archived", force=True)
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is True
        status_check = next(c for c in result["checks"] if c["name"] == "archive_status")
        assert "overridden by --force" in status_check["detail"]

    def test_empty_status_fails_without_force(self) -> None:
        """Empty archive_status fails without force."""
        ctx = _make_context(archive_status="", force=False)
        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is False


# =========================================================================
# Real-logic tests (other checks)
# =========================================================================


class TestL2OtherChecks:
    """Other field validation checks in L2."""

    def test_missing_archive_path_fails(self) -> None:
        """Missing archive_path fails."""
        ctx = _make_context(archive_path="")
        result = L2ArchiveValidation().execute(ctx)
        ap = next(c for c in result["checks"] if c["name"] == "archive_path_exists")
        assert ap["passed"] is False

    def test_incomplete_metadata_fails(self) -> None:
        """Missing required metadata fields fails."""
        ctx = _make_context(archive_metadata={"title": "Only Title"})
        result = L2ArchiveValidation().execute(ctx)
        mc = next(c for c in result["checks"] if c["name"] == "archive_metadata_complete")
        assert mc["passed"] is False

    def test_complete_metadata_passes(self) -> None:
        """All required metadata fields present passes."""
        ctx = _make_context(
            archive_metadata={
                "title": "Test",
                "platform": "wechat",
                "created_at": "2026-07-07T10:00:00",
            }
        )
        result = L2ArchiveValidation().execute(ctx)
        mc = next(c for c in result["checks"] if c["name"] == "archive_metadata_complete")
        assert mc["passed"] is True

    def test_empty_version_present_fails(self) -> None:
        """archive_version present but empty fails."""
        ctx = _make_context(archive_version="")
        result = L2ArchiveValidation().execute(ctx)
        av = next(c for c in result["checks"] if c["name"] == "archive_version_valid")
        assert av["passed"] is True  # Empty version is treated as not provided

    def test_missing_output_dir_fails(self) -> None:
        """Missing output directory fails."""
        ctx = _make_context(output_dir="")
        result = L2ArchiveValidation().execute(ctx)
        od = next(c for c in result["checks"] if c["name"] == "output_directory_exists")
        assert od["passed"] is False


# =========================================================================
# Result structure
# =========================================================================


class TestL2ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L2ArchiveValidation().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L2ArchiveValidation().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_six_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L2ArchiveValidation().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES


# =========================================================================
# Edge cases
# =========================================================================


class TestL2EdgeCases:
    """Edge-case handling."""

    def test_empty_context_does_not_crash(self) -> None:
        """Empty gate_context doesn't crash."""
        result = L2ArchiveValidation().execute({})
        assert result["gate"] == "L2"
        assert isinstance(result["checks"], list)
        assert result["passed"] is False

    def test_force_false_explicitly(self) -> None:
        """force=False explicitly is handled."""
        ctx = _make_context(archive_status="draft", force=False)
        result = L2ArchiveValidation().execute(ctx)
        assert result["passed"] is False

    def test_force_true_with_published(self) -> None:
        """force=True with published status still passes."""
        ctx = _make_context(archive_status="published", force=True)
        result = L2ArchiveValidation().execute(ctx)
        assert result["passed"] is True

    def test_mock_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim."""
        mock = _all_pass_mock()
        mock["archive_path_exists"] = {"passed": False, "detail": "custom path error"}
        ctx = _make_context(mock_results=mock)
        result = L2ArchiveValidation().execute(ctx)
        ap = next(c for c in result["checks"] if c["name"] == "archive_path_exists")
        assert ap["detail"] == "custom path error"
