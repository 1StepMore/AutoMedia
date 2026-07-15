#!/usr/bin/env python3
"""Verify that all three Omni packages (opp, ol_mcp, orf) are installed and functional.

Exit codes:
    0 — all packages verified
    1 — one or more packages missing or broken
"""

from __future__ import annotations

import sys


def _check_opp() -> list[str]:
    """Verify the ``opp`` (omni-pre-processor) package."""
    errors: list[str] = []
    try:
        import opp  # noqa: F401 — ensure top-level import works
    except ImportError:
        errors.append("opp package (omni-pre-processor) — not installed")
        return errors

    from opp import extractors as _extractors

    # At least one extractor class should be registered
    extractor_names = getattr(_extractors, "__all__", [])
    if not extractor_names:
        errors.append("opp.extractors.__all__ is empty — no extractors registered")

    return errors


def _check_ol_mcp() -> list[str]:
    """Verify the ``ol_mcp`` (omni-localizer) package."""
    errors: list[str] = []
    try:
        import ol_mcp  # noqa: F401
    except ImportError:
        errors.append("ol_mcp package (omni-localizer) — not installed")
        return errors

    # Check that the core translate function exists
    try:
        from ol_mcp.translate_md import _translate_single  # noqa: F401
    except ImportError:
        errors.append("ol_mcp.translate_md._translate_single — import failed")

    return errors


def _check_orf() -> list[str]:
    """Verify the ``orf`` (omni-re-formatter) package."""
    errors: list[str] = []
    try:
        import orf  # noqa: F401
    except ImportError:
        errors.append("orf package (omni-re-formatter) — not installed")
        return errors

    from orf.converters.base import ConverterOptions
    from orf.converters.chunked_md_converter import ChunkedMDConverter

    # Instantiate the converter
    converter = ChunkedMDConverter()
    # Verify it has the expected method
    if not hasattr(converter, "convert"):
        errors.append("orf ChunkedMDConverter missing .convert() method")

    # Verify ConverterOptions can be constructed
    opts = ConverterOptions()
    if not hasattr(opts, "__dict__"):
        errors.append("orf ConverterOptions has unexpected type")

    return errors


def main() -> int:
    """Run all checks and report results."""
    checks = [
        ("opp (omni-pre-processor)", _check_opp),
        ("ol_mcp (omni-localizer)", _check_ol_mcp),
        ("orf (omni-re-formatter)", _check_orf),
    ]

    all_errors: list[tuple[str, list[str]]] = []
    all_ok = True

    print("=== Omni Packages Verification ===")
    print()

    for name, check_fn in checks:
        errors = check_fn()
        if errors:
            all_errors.append((name, errors))
            all_ok = False

    if all_ok:
        print("  ✓  All 3 Omni packages verified successfully")
        return 0

    print(f"  ✗  {len(all_errors)} package(s) with issues:\n")
    for name, errors in all_errors:
        print(f"     {name}:")
        for err in errors:
            print(f"       - {err}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
