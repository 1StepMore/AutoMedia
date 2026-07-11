"""Verify the asset_library public API surface matches __all__."""

from __future__ import annotations


class TestAssetLibraryExports:
    """__all__ should list every name that is importable from the package."""

    def test_all_matches_exported_names(self) -> None:
        """Every name in __all__ must be importable from automedia.asset_library."""
        import automedia.asset_library as pkg

        for name in pkg.__all__:
            assert hasattr(pkg, name), f"{name!r} in __all__ but not importable"
