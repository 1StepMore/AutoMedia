"""L2 Archive Validation Gate — strong archive validation.

Red Line 8: Rejects archives whose status is not ``"published"`` unless the
``--force`` flag is present in the gate context.
"""

from __future__ import annotations

from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import _derive_expected, build_gate_result
from automedia.gates.base import BaseGate

# ---------------------------------------------------------------------------
# Check names
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "archive_status",
    "force_flag",
    "archive_path_exists",
    "archive_metadata_complete",
    "archive_version_valid",
    "output_directory_exists",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _check_archive_status(context: GateContext | dict[str, Any]) -> dict[str, Any]:
    """Red Line 8: archive must have status ``"published"``.

    If status is not ``"published"`` this check fails. The overall pipeline
    may still pass if ``--force`` is set (handled by ``_check_force_flag``).
    """
    name = "archive_status"
    status = context.get("archive_status", "")
    if status == "published":
        return {"name": name, "passed": True, "detail": "archive status is 'published'"}
    return {
        "name": name,
        "passed": False,
        "detail": f"archive status is '{status}', expected 'published'",
    }


def _check_force_flag(context: GateContext | dict[str, Any]) -> dict[str, Any]:
    """Check whether the ``--force`` / ``force`` flag is set.

    When true this overrides a non-published archive status (Red Line 8).
    """
    name = "force_flag"
    force = context.get("force", False)
    if force:
        return {
            "name": name,
            "passed": True,
            "detail": "--force flag is set, overriding archive status",
        }
    return {
        "name": name,
        "passed": True,
        "detail": "no --force flag (archive status must be 'published')",
    }


def _check_archive_path_exists(context: GateContext | dict[str, Any]) -> dict[str, Any]:
    """Check that an archive path has been provided."""
    name = "archive_path_exists"
    path = context.get("archive_path", "")
    if isinstance(path, str) and len(path.strip()) > 0:
        return {"name": name, "passed": True, "detail": f"archive_path '{path}' provided"}
    return {"name": name, "passed": False, "detail": "archive_path is missing or empty"}


def _check_archive_metadata_complete(context: GateContext | dict[str, Any]) -> dict[str, Any]:
    """Check that archive metadata contains required fields."""
    name = "archive_metadata_complete"
    metadata: dict[str, Any] = context.get("archive_metadata", {})
    required_fields = ["title", "platform", "created_at"]
    missing = [f for f in required_fields if f not in metadata]
    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"metadata missing required fields: {missing}",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(required_fields)} required metadata fields present",
    }


def _check_archive_version_valid(context: GateContext | dict[str, Any]) -> dict[str, Any]:
    """Check that the archive version is a non-empty string if provided."""
    name = "archive_version_valid"
    version = context.get("archive_version", "")
    if not version:
        return {"name": name, "passed": True, "detail": "archive_version not provided (optional)"}
    if isinstance(version, str) and len(version.strip()) > 0:
        return {"name": name, "passed": True, "detail": f"archive_version '{version}' is valid"}
    return {"name": name, "passed": False, "detail": "archive_version is present but empty"}


def _check_output_directory_exists(context: GateContext | dict[str, Any]) -> dict[str, Any]:
    """Check that an output directory has been provided."""
    name = "output_directory_exists"
    out_dir = context.get("output_dir", "")
    if isinstance(out_dir, str) and len(out_dir.strip()) > 0:
        return {"name": name, "passed": True, "detail": f"output_dir '{out_dir}' provided"}
    return {"name": name, "passed": False, "detail": "output_dir is missing or empty"}


def _red_line_8_passes(context: GateContext | dict[str, Any]) -> bool:
    """Red Line 8: the archive passes validation iff it is published or force is on.

    This combines the two related checks into a single boolean for the
    top-level ``passed`` computation.
    """
    status_ok = context.get("archive_status", "") == "published"
    force_ok = context.get("force", False) is True
    return status_ok or force_ok


# ---------------------------------------------------------------------------
# L2ArchiveValidation gate
# ---------------------------------------------------------------------------


class L2ArchiveValidation(BaseGate):
    """L2 Archive Validation Gate — strong archive integrity checks.

    ``gate_context`` expected keys:
        - ``archive_status``: str — archive publication status
        - ``force``: bool — whether ``--force`` was passed (overrides status)
        - ``archive_path``: str — path to the archive
        - ``archive_metadata``: dict — metadata dict with title/platform/created_at
        - ``archive_version``: str — version string (optional)
        - ``output_dir``: str — output directory path
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` for deterministic testing.

    Red Line 8:
        Rejects archives whose ``archive_status`` is not ``"published"``
        unless ``force=True`` is set in the context.
    """

    _gate_name = "L2"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 6 archive validation checks and return structured result."""
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("archive_status", lambda: _check_archive_status(gate_context)),
            ("force_flag", lambda: _check_force_flag(gate_context)),
            ("archive_path_exists", lambda: _check_archive_path_exists(gate_context)),
            ("archive_metadata_complete", lambda: _check_archive_metadata_complete(gate_context)),
            ("archive_version_valid", lambda: _check_archive_version_valid(gate_context)),
            ("output_directory_exists", lambda: _check_output_directory_exists(gate_context)),
        ]

        checks: list[dict[str, Any]] = []
        for name, fn in check_fns:
            if mock_results is not None and name in mock_results:
                mock = mock_results[name]
                checks.append(
                    {
                        "name": name,
                        "passed": bool(mock["passed"]),
                        "detail": str(mock.get("detail", "")),
                    }
                )
            else:
                checks.append(fn())

        # Compute overall passed — Red Line 8 is enforced by combining the
        # archive_status and force_flag checks with the top-level combination.
        result = build_gate_result(checks, gate="L2")

        # Red Line 8 override: only apply to real logic (not mock-driven tests).
        # When mocks are present, we trust the mock values verbatim.
        if mock_results is None and not result["passed"] and _red_line_8_passes(gate_context):
            # Force overrides: mark archive_status check as passed
            for c in result["checks"]:
                if c["name"] == "archive_status":
                    c["passed"] = True
                    c["detail"] = "overridden by --force (Red Line 8 exemption)"
            result["passed"] = True
            first_pass = next(
                (c for c in result["checks"] if c["passed"]),
                result["checks"][0] if result["checks"] else None,
            )
            if first_pass:
                result["expected_vs_actual"] = {
                    "check": first_pass["name"],
                    "expected": _derive_expected(first_pass["name"]),
                    "actual": first_pass.get("detail", ""),
                    "context": {},
                }

        return result
