"""ORF adapter — wraps omni-re-formatter for document format conversion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.omni.base import BaseOmniAdapter

log = get_logger(__name__)


class ORFAdapter(BaseOmniAdapter):
    @property
    def name(self) -> str:
        """Return the adapter identifier ``"orf"``."""
        return "orf"

    def validate_env(self) -> bool:
        """Check that ``MCP_ALLOWED_DIRECTORIES`` is set for ORF operations.

        Returns ``True`` when the environment variable is present.
        """
        return "MCP_ALLOWED_DIRECTORIES" in os.environ

    def convert(
        self,
        file_path: str,
        output_path: str | None = None,
        **options: Any,  # noqa: ANN401 — pass-through to orf library
    ) -> dict[str, Any]:
        """Convert a file to target format.

        Returns a result dict.  If the ``orf`` package is not installed the
        method logs a warning and returns an error result — it never raises.
        """
        try:
            from orf.converters.base import ConverterOptions
            from orf.converters.chunked_md_converter import ChunkedMDConverter
        except ImportError:
            from automedia.core._import_helpers import warn_missing_optional

            warn_missing_optional("orf", feature="ORF format conversion disabled")
            return {
                "status": "error",
                "output_path": "",
                "success": False,
                "errors": [
                    "orf package not available — ORF conversion disabled. "
                    "Install with: pip install automedia-pipeline[omni]"
                ],
            }

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

    def apply_md(self, md_content: str, target_path: str) -> str:
        """Write markdown content to *target_path*, creating dirs as needed."""
        parent = os.path.dirname(target_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as fh:
            fh.write(md_content)
        return target_path


