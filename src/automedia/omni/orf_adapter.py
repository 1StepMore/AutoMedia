"""ORF adapter — wraps omni-re-formatter for document format conversion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from automedia.omni.base import BaseOmniAdapter


class ORFAdapter(BaseOmniAdapter):
    @property
    def name(self) -> str:
        return "orf"

    def validate_env(self) -> bool:
        import os

        return "MCP_ALLOWED_DIRECTORIES" in os.environ

    def convert(
        self,
        file_path: str,
        output_path: str | None = None,
        **options: Any,  # noqa: ANN401 — pass-through
    ) -> dict[str, Any]:
        """Convert a file to target format."""
        from orf.converters.base import ConverterOptions
        from orf.converters.chunked_md_converter import ChunkedMDConverter

        converter = ChunkedMDConverter()
        opts: ConverterOptions | None = ConverterOptions(**options) if options else None
        result = converter.convert(
            input_path=Path(file_path),
            output_path=Path(output_path) if output_path else Path(file_path + ".out"),
            options=opts,
        )
        return {
            "status": "ok" if result.success else "error",
            "output_path": str(result.output_path),
            "success": result.success,
            "errors": [str(e) for e in result.errors] if result.errors else [],
        }

    def backfill(
        self,
        translated_md: str,
        original_md: str,
        skeleton_path: str | None = None,
    ) -> str:
        """Backfill translated markdown using original + skeleton.

        Stub — returns translated_md as-is. Real skeleton-based backfill
        will be implemented later.
        """
        return translated_md

    def apply_md(self, md_content: str, target_path: str) -> str:
        """Write markdown content to *target_path*, creating dirs as needed."""
        parent = os.path.dirname(target_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as fh:
            fh.write(md_content)
        return target_path

    def apply_xliff(self, xliff_path: str, output_dir: str) -> str:
        """Placeholder — real XLIFF backfill not yet implemented."""
        base = os.path.splitext(os.path.basename(xliff_path))[0]
        output_path = os.path.join(output_dir, base + ".backfilled.md")
        print(f"[ORFAdapter] apply_xliff is a placeholder — no-op for {xliff_path}")
        return output_path
