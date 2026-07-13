"""OL adapter — wraps omni-localizer for document translation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import override

from automedia.omni.base import BaseOmniAdapter


@dataclass
class TranslationResult:
    """Result of an OL document translation."""

    translated_md: str
    xliff_path: str | None = None
    warnings: list[str] = field(default_factory=list)


class OLAdapter(BaseOmniAdapter):
    config_path: str

    def __init__(self, config_path: str = "ol_config.yaml") -> None:
        """Initialize the OL adapter with a path to the OL config YAML."""
        super().__init__()
        self.config_path = config_path

    @property
    @override
    def name(self) -> str:
        """Return the adapter identifier ``"ol"``."""
        return "ol"

    @override
    def validate_env(self) -> bool:
        """Check that ``MCP_ALLOWED_DIRECTORIES`` is set for OL operations.

        fail-CLOSED: require the env var so the OL pipeline's security
        validator has a path allowlist to check.

        Returns ``True`` when the environment variable is present.
        """
        import os

        return "MCP_ALLOWED_DIRECTORIES" in os.environ

    def translate(
        self,
        md_content: str,
        source_lang: str = "auto",
        target_lang: str = "auto",
        config_path: str | None = None,
    ) -> TranslationResult:
        """Translate *md_content* from *source_lang* to *target_lang*.

        Uses OL's shield → LLM-translate → repair → unshield pipeline.

        Parameters
        ----------
        md_content : str
            Markdown content to translate.
        source_lang : str
            Source language code (default: ``"auto"``).
        target_lang : str
            Target language code (default: ``"auto"``).
        config_path : str | None
            Path to the OL configuration YAML. If ``None``,
            falls back to ``self.config_path``.

        Returns
        -------
        TranslationResult
            Translated markdown, optional XLIFF path, and warnings.

        Raises
        ------
        ValueError
            If no ``config_path`` is provided and ``self.config_path``
            is also not set.
        """
        # Lazy imports — the full OL dependency tree is heavy and should
        # not be pulled in at module load time.
        try:
            from ol_mcp.translate_md import _translate_single
        except ImportError:
            # When ol_mcp is not installed, check if the config path at least
            # exists so we can report the right warning.
            resolved = config_path or self.config_path
            if resolved and not Path(resolved).is_file():
                return TranslationResult(
                    translated_md="",
                    warnings=[
                        f"Config not found at {resolved}."
                        " Check the path or set config_path explicitly."
                    ],
                )
            from automedia.core._import_helpers import warn_missing_optional

            warn_missing_optional("ol_mcp", feature="OL translation disabled")
            return TranslationResult(
                translated_md="",
                warnings=[
                    "ol_mcp package not available — OL translation disabled. "
                    "Install with: pip install automedia-pipeline[omni]"
                ],
            )

        resolved = config_path or self.config_path
        if not resolved:
            raise ValueError(
                "No config_path provided to translate() and no config_path "
                + "set on OLAdapter instance."
            )

        try:

            async def _run() -> tuple[str, list[str]]:
                """Execute the OL translation pipeline asynchronously."""
                translated, warnings = await _translate_single(
                    content=md_content,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    glossary=None,
                    config_path=resolved,
                )
                return translated, warnings

            translated, warnings = asyncio.run(_run())
        except FileNotFoundError:
            return TranslationResult(
                translated_md="",
                warnings=[
                    f"Config not found at {resolved}. Check the path or set config_path explicitly."
                ],
            )
        except Exception as e:
            return TranslationResult(
                translated_md="",
                warnings=[f"Translation failed: {e}"],
            )
        return TranslationResult(
            translated_md=translated,
            xliff_path=None,
            warnings=warnings if warnings else [],
        )

    def translate_batch(
        self,
        file_list: list[str],
        source_lang: str = "auto",
        target_lang: str = "auto",
    ) -> list[TranslationResult]:
        """Translate a batch of files, returning one :class:`TranslationResult` per file.

        Files that cannot be read are skipped with a warning entry.
        """
        results: list[TranslationResult] = []
        for path in file_list:
            try:
                content = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                results.append(
                    TranslationResult(
                        translated_md="",
                        xliff_path=None,
                        warnings=[f"File not found: {path}"],
                    )
                )
                continue
            result = self.translate(
                md_content=content,
                source_lang=source_lang,
                target_lang=target_lang,
            )
            results.append(result)
        return results


