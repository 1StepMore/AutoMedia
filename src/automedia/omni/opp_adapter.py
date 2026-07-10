"""OPP adapter — wraps omni-pre-processor for document extraction."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from automedia.omni.base import BaseOmniAdapter


@dataclass
class ExtractionResult:
    """Result of an OPP document extraction."""

    md_content: str
    manifest: dict[str, Any]
    xliff_path: str | None = None
    skeleton_path: str | None = None
    warnings: list[str] = field(default_factory=list)


class OPPAdapter(BaseOmniAdapter):
    @property
    def name(self) -> str:
        return "opp"

    def validate_env(self) -> bool:
        return True

    def extract(
        self, file_path: str, source_lang: str = "auto", target_lang: str = "auto"
    ) -> ExtractionResult:
        """Extract content from a document file using OPP."""
        try:
            _ensure_extractor_map()
            ext = os.path.splitext(file_path)[1].lower()
            cls = _EXTRACTOR_MAP.get(ext)
            if cls is not None:
                from pathlib import Path

                extractor = cls()
                result = extractor.extract(Path(file_path))
                return self.extract_md(
                    result.content, source_lang=source_lang, target_lang=target_lang
                )
            # No extractor found — read file as markdown
            with open(file_path, encoding="utf-8") as fh:
                md_content = fh.read()
            return self.extract_md(md_content, source_lang=source_lang, target_lang=target_lang)
        except Exception as e:
            return ExtractionResult(
                md_content="", manifest={"error": str(e)}, warnings=[f"Extraction failed: {e}"]
            )

    def extract_md(
        self,
        md_content: str,
        source_lang: str = "auto",
        target_lang: str = "auto",
    ) -> ExtractionResult:
        """Extract and structure markdown content, returning an ExtractionResult.

        Calls existing internal logic then wraps the outcome in an
        ``ExtractionResult`` so callers receive a typed container instead of a
        plain dict.
        """
        segments = _parse_md_to_segments(md_content)
        manifest: dict[str, Any] = {
            "segments": segments,
            "source_lang": source_lang,
            "target_lang": target_lang,
        }
        return ExtractionResult(
            md_content=md_content,
            manifest=manifest,
            xliff_path=None,
            skeleton_path=None,
            warnings=[],
        )

    def batch_extract(
        self,
        file_list: list[str],
        source_lang: str = "auto",
        target_lang: str = "auto",
    ) -> list[ExtractionResult]:
        """Extract content from multiple files.

        Reads each file, delegates to :meth:`extract_md`, and collects results.
        Files that cannot be read are skipped with a warning recorded in the
        returned ``ExtractionResult.warnings`` list.
        """
        results: list[ExtractionResult] = []
        for file_path in file_list:
            try:
                with open(file_path, encoding="utf-8") as fh:
                    md_content = fh.read()
            except FileNotFoundError:
                results.append(
                    ExtractionResult(
                        md_content="",
                        manifest={},
                        warnings=[f"FileNotFoundError: {file_path}"],
                    )
                )
                continue
            results.append(
                self.extract_md(md_content, source_lang=source_lang, target_lang=target_lang)
            )
        return results

    def detect_format(self, md_content: str) -> str:
        """Detect the document format of *md_content*.

        Stub implementation — always returns ``"markdown"``.  Real detection
        via LLM will be added later.
        """
        return "markdown"


def _parse_md_to_segments(md_content: str) -> list[dict[str, Any]]:
    """Parse markdown content into a list of segment dicts.

    Each segment is ``{"index": int, "text": str}``.  Lines are treated as
    individual segments.  This is a lightweight placeholder — richer parsing
    (heading hierarchy, fenced blocks, etc.) can be layered on later.
    """
    segments: list[dict[str, Any]] = []
    for idx, line in enumerate(md_content.splitlines()):
        segments.append({"index": idx, "text": line})
    return segments


_EXTRACTOR_MAP: dict[str, type] = {}


def _ensure_extractor_map() -> None:
    if _EXTRACTOR_MAP:
        return
    from opp import extractors as _extractors

    for _name in _extractors.__all__:
        _cls = getattr(_extractors, _name, None)
        if _cls is None:
            continue
        try:
            _instance = _cls()
        except Exception:  # noqa: S112 — skip broken extractors
            continue
        try:
            _exts = _instance.supported_extensions()
        except Exception:  # noqa: S112 — skip broken extractors
            continue
        for _ext in _exts:
            _EXTRACTOR_MAP[_ext.lower()] = _cls
