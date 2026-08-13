"""Omni Triad MCP tool handlers — extraction, localization, format conversion."""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.core.llm_client import LLMError
from automedia.exceptions import AutoMediaError
from automedia.mcp.tools._shared import (
    _ALLOWED_OUTPUT_FORMATS,
    MCPErrorCode,
    _require_allowed,
    error_response,
    success_response,
)

log = get_logger(__name__)


def extract_brief(
    file_path: str,
    source_lang: str = "auto",
    target_lang: str = "en",
) -> dict[str, Any]:
    """Extract a content brief from a document file using OPP.

    Processes the document through OPPAdapter.extract() to extract
    structured markdown content, a manifest JSON with segment metadata,
    and any warnings encountered during extraction.

    Parameters
    ----------
    file_path:
        Path to the source document file.
    source_lang:
        Source language code (``"auto"`` for auto-detection).
    target_lang:
        Target language code for extraction (default ``"en"``).

    Returns
    -------
    dict
        ``{"md_content": str, "manifest_json": dict, "warnings": list[str]}``
        or an error dict on failure.
    """
    try:
        _require_allowed(file_path, tool_name="extract_brief")
        from automedia.omni.opp_adapter import OPPAdapter

        adapter = OPPAdapter()
        result = adapter.extract(file_path, source_lang, target_lang)
        return success_response(
            {
                "md_content": result.md_content,
                "manifest_json": result.manifest,
                "warnings": result.warnings,
            }
        )
    except OSError as exc:
        return {
            "md_content": "",
            "manifest_json": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}"),
        }
    except ImportError as exc:
        return {
            "md_content": "",
            "manifest_json": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "md_content": "",
            "manifest_json": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


def localize_content(
    md_content: str,
    source_lang: str,
    target_lang: str,
) -> dict[str, Any]:
    """Translate markdown content from source to target language.

    Delegates to OLAdapter.translate() which uses the OL shield →
    LLM-translate → repair → unshield pipeline.  Returns the translated
    markdown, optional XLIFF path, and any warnings collected.

    Parameters
    ----------
    md_content:
        Source markdown content to translate.
    source_lang:
        Source language code (e.g. ``"zh"``, ``"ja"``).
    target_lang:
        Target language code (e.g. ``"en"``).

    Returns
    -------
    dict
        ``{"translated_md": str, "xliff_path": str | None, "warnings": list[str]}``
        or an error dict on failure.
    """
    try:
        from automedia.omni.ol_adapter import OLAdapter

        adapter = OLAdapter()
        result = adapter.translate(md_content, source_lang, target_lang)
        return success_response(
            {
                "translated_md": result.translated_md,
                "xliff_path": result.xliff_path,
                "warnings": result.warnings,
            }
        )
    except ImportError as exc:
        return {
            "translated_md": "",
            "xliff_path": None,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except LLMError as exc:
        return {
            "translated_md": "",
            "xliff_path": None,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "translated_md": "",
            "xliff_path": None,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


def localize_output(
    project_dir: str,
    target_langs: str,
) -> dict[str, Any]:
    """Translate all project drafts into multiple target languages.

    Reads markdown files from ``01_content/drafts/``, translates each into
    every target language via OLAdapter, writes to ``05_publish/{lang}/``,
    and returns a mapping of language → output file paths.

    Parameters
    ----------
    project_dir:
        Path to the project root directory.
    target_langs:
        Comma-separated language codes (e.g. ``"en,ja"``).

    Returns
    -------
    dict
        ``{"project_dir": str, "results": {lang: [file_path, ...]}, "warnings": [...]}``
        or error dict.
    """
    try:
        _require_allowed(project_dir, tool_name="localize_output")
        from pathlib import Path

        from automedia.omni.ol_adapter import OLAdapter

        proj = Path(project_dir)
        drafts_dir = proj / "01_content" / "drafts"

        results: dict[str, list[str]] = {}
        warnings: list[str] = []

        if not drafts_dir.is_dir():
            return success_response(
                {
                    "project_dir": project_dir,
                    "results": results,
                    "warnings": [f"Drafts directory not found: {drafts_dir}"],
                }
            )

        langs = [lang.strip() for lang in target_langs.split(",") if lang.strip()]
        if not langs:
            return success_response(
                {
                    "project_dir": project_dir,
                    "results": results,
                    "warnings": ["No target languages specified"],
                }
            )

        md_files = sorted(drafts_dir.glob("*.md"))
        if not md_files:
            return success_response(
                {
                    "project_dir": project_dir,
                    "results": results,
                    "warnings": [f"No markdown files found in {drafts_dir}"],
                }
            )

        adapter = OLAdapter()

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            for lang in langs:
                try:
                    trans_result = adapter.translate(
                        md_content=content,
                        source_lang="auto",
                        target_lang=lang,
                    )
                    publish_dir = proj / "05_publish" / lang
                    publish_dir.mkdir(parents=True, exist_ok=True)
                    output_file = publish_dir / md_file.name
                    output_file.write_text(trans_result.translated_md, encoding="utf-8")
                    results.setdefault(lang, []).append(str(output_file))
                except Exception as exc:
                    # Per-file catch-all: one file failure doesn't stop other translations
                    warnings.append(f"Translation failed for {md_file.name} \u2192 {lang}: {exc}")

        return success_response(
            {
                "project_dir": project_dir,
                "results": results,
                "warnings": warnings,
            }
        )
    except OSError as exc:
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}"),
        }
    except LLMError as exc:
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


def format_output(
    content: str,
    target_format: str,
    **options: Any,  # noqa: ANN401 — pass-through to ORFAdapter.convert()
) -> dict[str, Any]:
    """Convert content to the specified output format.

    Delegates to ORFAdapter.convert() to transform content into the
    requested output format.  Returns the output path, format identifier,
    and any warnings or errors encountered during conversion.

    Parameters
    ----------
    content:
        Source content to convert (markdown text).
    target_format:
        Desired output format identifier (e.g. ``"html"``, ``"pdf"``).
    **options:
        Additional keyword arguments forwarded to the converter.

    Returns
    -------
    dict
        ``{"output_path": str, "output_format": str, "warnings": list[str]}``
        or an error dict on failure.
    """
    if "/" in target_format or "\\" in target_format or ".." in target_format:
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"Invalid format: {target_format!r} — path separators not allowed",
        )

    if target_format not in _ALLOWED_OUTPUT_FORMATS:
        return error_response(MCPErrorCode.INVALID_PARAM, f"Unsupported format: {target_format!r}")

    import tempfile

    temp_path: str | None = None
    try:
        from automedia.omni.orf_adapter import ORFAdapter

        # Compute the output path explicitly based on the target format.
        # ORFAdapter.convert expects a file path; write content to a
        # temporary file, then delete it after conversion completes.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(content)
            temp_path = fh.name

        output_path = temp_path + "." + target_format
        adapter = ORFAdapter()
        result = adapter.convert(
            file_path=temp_path,
            output_path=output_path,
            **options,
        )
        errors = result.get("errors", [])
        return success_response(
            {
                "output_path": output_path,
                "output_format": target_format,
                "warnings": errors if errors else [],
            }
        )
    except ImportError as exc:
        return {
            "output_path": "",
            "output_format": target_format,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except AutoMediaError as exc:
        return {
            "output_path": "",
            "output_format": target_format,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "output_path": "",
            "output_format": target_format,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }
    finally:
        if temp_path is not None:
            try:
                import os

                os.unlink(temp_path)
            except OSError:
                log.warning("Failed to clean up temp file %s", temp_path)
