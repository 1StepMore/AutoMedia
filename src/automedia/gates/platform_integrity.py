"""L3 Platform Integrity Gate — platform material completeness.

Ensures that the archive covers all required platforms as a single unified
archive without splitting content per platform.
"""

from __future__ import annotations

from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate

# ---------------------------------------------------------------------------
# Check names
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "all_platforms_present",
    "no_platform_splitting",
    "material_integrity",
    "cross_platform_consistency",
    "format_completeness",
    "metadata_integrity",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _check_all_platforms_present(context: dict[str, Any]) -> dict[str, Any]:
    """Check that all expected platforms are covered in the archive."""
    name = "all_platforms_present"
    platforms: list[str] = context.get("platforms", [])
    expected: list[str] = context.get("expected_platforms", [])

    if not expected:
        return {"name": name, "passed": True, "detail": "no expected_platforms specified, skipping"}

    missing = [p for p in expected if p not in platforms]
    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"missing platforms: {missing}",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(expected)} expected platforms present: {expected}",
    }


def _check_no_platform_splitting(context: dict[str, Any]) -> dict[str, Any]:
    """Ensure content is NOT split per platform — must be a single unified archive.

    If ``content_platform_map`` exists and maps content to specific platforms,
    that indicates splitting, which is forbidden.
    """
    name = "no_platform_splitting"
    platform_map: dict[str, Any] = context.get("content_platform_map", {})

    if platform_map:
        return {
            "name": name,
            "passed": False,
            "detail": f"content is split across platforms: {list(platform_map)}",
        }

    unified_content = context.get("unified_content", "")
    if not isinstance(unified_content, str) or len(unified_content.strip()) == 0:
        return {
            "name": name,
            "passed": False,
            "detail": "unified_content is missing or empty — archive may be split",
        }

    return {
        "name": name,
        "passed": True,
        "detail": "content is a single unified archive, no platform splitting detected",
    }


def _check_material_integrity(context: dict[str, Any]) -> dict[str, Any]:
    """Verify that all referenced media files are present."""
    name = "material_integrity"
    media_files: list[str] = context.get("media_files", [])

    if not media_files:
        return {"name": name, "passed": True, "detail": "no media_files to verify (empty archive)"}

    file_paths: list[str] = context.get("file_paths", [])

    missing: list[str] = []
    for f in media_files:
        if f not in file_paths:
            missing.append(f)

    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"referenced media files not found in archive: {missing}",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(media_files)} media files present in archive",
    }


def _check_cross_platform_consistency(context: dict[str, Any]) -> dict[str, Any]:
    """Ensure content is consistent across all platforms (same core content)."""
    name = "cross_platform_consistency"
    platform_variants: dict[str, str] = context.get("platform_variants", {})

    if len(platform_variants) <= 1:
        return {
            "name": name,
            "passed": True,
            "detail": "single platform or no variants — consistent",
        }

    variants = list(platform_variants.values())
    reference = variants[0]
    inconsistencies: list[str] = []
    for plat, variant in platform_variants.items():
        # Simple check: length ratio should not differ by more than 50%
        if len(variant) < len(reference) * 0.5 or len(variant) > len(reference) * 1.5:
            inconsistencies.append(plat)

    if inconsistencies:
        return {
            "name": name,
            "passed": False,
            "detail": f"platform variants with inconsistent length: {inconsistencies}",
        }
    return {"name": name, "passed": True, "detail": "content is consistent across platforms"}


def _check_format_completeness(context: dict[str, Any]) -> dict[str, Any]:
    """Check that all required output formats are specified."""
    name = "format_completeness"
    formats: list[str] = context.get("formats", [])
    required_formats: list[str] = context.get("required_formats", ["mp4", "txt", "json"])

    if not formats:
        return {"name": name, "passed": False, "detail": "no formats specified"}

    if required_formats:
        missing = [f for f in required_formats if f not in formats]
        if missing:
            return {
                "name": name,
                "passed": False,
                "detail": f"required formats missing: {missing}",
            }

    return {
        "name": name,
        "passed": True,
        "detail": f"all required formats present: {formats}",
    }


def _check_metadata_integrity(context: dict[str, Any]) -> dict[str, Any]:
    """Check that the archive metadata is internally consistent."""
    name = "metadata_integrity"
    metadata: dict[str, Any] = context.get("archive_metadata", {})

    required_fields = ["title", "platform", "created_at"]
    missing = [f for f in required_fields if f not in metadata]
    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"archive_metadata missing: {missing}",
        }

    # Check platform consistency
    archive_platform = metadata.get("platform")
    platforms = context.get("platforms", [])
    if archive_platform and platforms and archive_platform not in platforms:
        return {
            "name": name,
            "passed": False,
            "detail": (
                f"archive_metadata.platform '{archive_platform}' not in platforms list {platforms}"
            ),
        }

    return {"name": name, "passed": True, "detail": "metadata is internally consistent"}


# ---------------------------------------------------------------------------
# L3PlatformIntegrity gate
# ---------------------------------------------------------------------------


class L3PlatformIntegrity(BaseGate):
    """L3 Platform Integrity Gate — platform material completeness.

    ``gate_context`` expected keys:
        - ``platforms``: list[str] — platforms targeted by this archive
        - ``expected_platforms``: list[str] — platforms that should be covered
        - ``content_platform_map``: dict — platform→content mapping (forbidden)
        - ``unified_content``: str — the single unified content body
        - ``media_files``: list[str] — referenced media file names
        - ``file_paths``: list[str] — actual file paths in the archive
        - ``platform_variants``: dict[str, str] — platform→variant content
        - ``formats``: list[str] — output formats specified
        - ``required_formats``: list[str] — formats that must be present
        - ``archive_metadata``: dict — archive metadata
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` for deterministic testing.
    """

    _gate_name = "L3"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 6 platform integrity checks and return structured result."""
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("all_platforms_present", lambda: _check_all_platforms_present(gate_context)),
            ("no_platform_splitting", lambda: _check_no_platform_splitting(gate_context)),
            ("material_integrity", lambda: _check_material_integrity(gate_context)),
            ("cross_platform_consistency", lambda: _check_cross_platform_consistency(gate_context)),
            ("format_completeness", lambda: _check_format_completeness(gate_context)),
            ("metadata_integrity", lambda: _check_metadata_integrity(gate_context)),
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

        return build_gate_result(checks, gate="L3")
