"""OL adapter — wraps omni-localizer for document translation."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from structlog import get_logger
from typing_extensions import override

from automedia.omni.base import BaseOmniAdapter

log = get_logger(__name__)

_OL_CONFIG_ENV = "AUTOMEDIA_OL_CONFIG"
_OL_CONFIG_NAME = "ol_config.yaml"


def _home_root() -> Path:
    """``$HOME`` when set, else the platform home directory.

    ``Path.home()`` reads ``USERPROFILE`` on Windows and ignores ``$HOME``,
    which breaks the POSIX convention (and every test harness that only sets
    ``$HOME``).  Honor ``$HOME`` first on every platform; Git Bash/MSYS
    Windows sessions set it too, so this is strictly more correct there as
    well.
    """
    home = os.environ.get("HOME", "").strip()
    return Path(home) if home else Path.home()


def resolve_config_path(explicit: str | None = None) -> str | None:
    """Resolve the OL config YAML path through a fixed precedence ladder.

    Order:

    1. *explicit* (returned as-is when provided)
    2. ``AUTOMEDIA_OL_CONFIG`` environment variable
    3. ``ol_config.yaml`` in the current working directory (when it exists)
    4. ``~/.automedia/omni/ol_config.yaml`` (when it exists)

    Returns ``None`` when no candidate is available.  Explicit/environment
    values are not existence-checked so ``translate`` can report a precise
    "Config not found" warning instead of silently falling through.
    """
    if explicit:
        return explicit

    from_env = os.environ.get(_OL_CONFIG_ENV, "").strip()
    if from_env:
        return from_env

    cwd_config = Path.cwd() / _OL_CONFIG_NAME
    if cwd_config.is_file():
        return str(cwd_config)

    home_config = _home_root() / ".automedia" / "omni" / _OL_CONFIG_NAME
    if home_config.is_file():
        return str(home_config)

    return None


def stamp_translation_frontmatter(md: str, source_lang: str, target_lang: str) -> str:
    """Ensure *md* carries ``source_lang`` / ``target_lang`` YAML frontmatter.

    - Empty (or whitespace-only) content is returned unchanged.
    - Without frontmatter, a new block is prepended.
    - With frontmatter, other keys are preserved and the two language keys
      are overwritten.
    """
    if not md.strip():
        return md

    header = f"---\nsource_lang: {source_lang}\ntarget_lang: {target_lang}\n---\n"

    if not md.startswith("---"):
        return header + "\n" + md

    second_dash = md.find("---", 3)
    if second_dash == -1:
        return header + "\n" + md

    raw_frontmatter = md[3:second_dash]
    body = md[second_dash + 3 :]

    try:
        loaded = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError:
        return header + "\n" + md

    data = loaded if isinstance(loaded, dict) else {}
    data["source_lang"] = source_lang
    data["target_lang"] = target_lang

    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    return f"---\n{dumped}---\n{body}"


@dataclass
class TranslationResult:
    """Result of an OL document translation."""

    translated_md: str
    xliff_path: str | None = None
    warnings: list[str] = field(default_factory=list)


def resolve_source_lang(source_lang: str = "") -> str:
    """Resolve the effective OL source language for translation and L4.

    Returns *source_lang* when it is a real language code; otherwise the merged
    config's ``content.default_language`` (``"zh"`` by default).  The literal
    sentinel ``"auto"`` is always resolved to the configured default: L4
    compares the expected ``source_lang`` against the frontmatter's real value,
    so the sentinel can never match and must never reach the gate or
    ``OLAdapter.translate``.
    """
    candidate = source_lang.strip()
    if candidate and candidate.lower() != "auto":
        return candidate

    from automedia.core.config_loader import load_config

    configured = str(load_config().get("content", {}).get("default_language", "")).strip()
    if not configured or configured.lower() == "auto":
        return "zh"
    return configured


class OLAdapter(BaseOmniAdapter):
    config_path: str

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the OL adapter with a path to the OL config YAML.

        An explicit *config_path* always wins.  Otherwise the path is
        resolved via :func:`resolve_config_path` (env → cwd →
        ``~/.automedia/omni/``), possibly becoming an empty string when no
        candidate exists.
        """
        super().__init__()
        self.config_path = config_path if config_path is not None else (resolve_config_path() or "")

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
            Translated markdown, optional XLIFF path, and warnings.  When no
            config path can be resolved, fake LLM mode returns the source
            unchanged as a deterministic passthrough; otherwise
            ``translated_md`` is empty and ``warnings`` explains why — no
            exception is raised.
        """
        resolved = config_path or self.config_path
        if not resolved:
            from automedia.core.llm_client import _is_fake_mode

            if _is_fake_mode():
                # FAKE_LLM: no network, no config required — pass the source
                # through and annotate it so downstream write paths can still
                # be exercised end-to-end deterministically.
                return TranslationResult(
                    translated_md=md_content,
                    warnings=["fake LLM mode: passthrough translation (no OL config required)"],
                )
            return TranslationResult(
                translated_md="",
                warnings=[
                    "Config not found: no OL config path available. "
                    "Set AUTOMEDIA_OL_CONFIG or create ~/.automedia/omni/ol_config.yaml."
                ],
            )

        # Lazy imports — the full OL dependency tree is heavy and should
        # not be pulled in at module load time.
        try:
            from ol_mcp.translate_md import _translate_single
        except ImportError:
            # When ol_mcp is not installed, check if the config path at least
            # exists so we can report the right warning.
            if not Path(resolved).is_file():
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
