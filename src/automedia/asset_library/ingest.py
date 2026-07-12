"""Ingestion — scan project directories and import artifacts into the Asset Library.

Scans a project directory for decision artifacts, extracts metadata,
computes MD5 checksums, and writes both to the SQLite database and
the Chroma vector store.

Artifact file discovery conventions
-----------------------------------
The ingester looks for files in these locations:

* ``decision/``  — DecisionAgent YAML/JSON/MD output files
* ``01_content/``, ``02_images/``, etc. — content pipeline outputs
* ``research_data/`` — Omni extraction outputs (see ``artifact_mapping``)
* ``*.md`` files at the project root (briefs, strategy docs)

Each file is mapped to an ``AssetDoc`` based on its path, extension,
and any embedded front-matter metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from automedia.asset_library.db import ASSET_TYPES, AssetDatabase, AssetDoc
from automedia.asset_library.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    """Result of an ingestion run.

    Attributes
    ----------
    success_count : int
        Number of artifacts successfully ingested.
    fail_count : int
        Number of artifacts that failed ingestion.
    errors : list[str]
        Human-readable error messages for each failure.
    """

    success_count: int = 0
    fail_count: int = 0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"IngestResult(success={self.success_count}, "
            f"fail={self.fail_count}, errors={len(self.errors)})"
        )


# ---------------------------------------------------------------------------
# Artifact type mapping
# ---------------------------------------------------------------------------

# Map file-name keywords and directory names to asset types.
_PATH_TYPE_HINTS: dict[str, str] = {
    "brief": "strategy",
    "strategy": "strategy",
    "brand_dna": "strategy",
    "market_report": "strategy",
    "persona": "persona",
    "persona_map": "persona",
    "competitor": "strategy",
    "competitor_matrix": "strategy",
    "product": "product",
    "content": "content",
    "kol": "kol_brief",
    "kol_brief": "kol_brief",
    "asset_blueprint": "asset",
    "asset": "asset",
    "content_calendar": "content",
}

# File extensions we recognise as artifact content.
_INGESTIBLE_EXTENSIONS = frozenset({".md", ".yaml", ".yml", ".json", ".csv"})


# ---------------------------------------------------------------------------
# Core ingestion logic
# ---------------------------------------------------------------------------


def ingest_artifacts(project_dir: str, brand: str) -> IngestResult:
    """Scan a project directory and ingest all discoverable artifacts.

    Parameters
    ----------
    project_dir : str
        Absolute or relative path to the project root.
    brand : str
        Brand identifier used for the database and vector store.

    Returns
    -------
    IngestResult
        Summary of the ingestion run.
    """
    result = IngestResult()

    root = Path(project_dir).resolve()
    if not root.is_dir():
        result.fail_count += 1
        result.errors.append(f"Project directory not found: {project_dir}")
        return result

    db = AssetDatabase(brand=brand)
    vs = VectorStore(brand=brand)

    try:
        artifacts = _discover_artifacts(root)
        if not artifacts:
            logger.info("No ingestible artifacts found in %s", root)
            return result

        for file_path, hints in artifacts:
            try:
                doc = _build_asset_doc(file_path, brand, hints)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result.fail_count += 1
                result.errors.append(f"Failed to read {file_path}: {exc}")
                continue

            # Skip duplicate content (same checksum already ingested).
            if db.asset_exists_by_checksum(doc.checksum):
                logger.debug("Skipping duplicate: %s", file_path)
                result.success_count += 1  # count as success (idempotent)
                continue

            # Write to SQLite.
            try:
                doc_id = db.add_asset(doc)
            except Exception as exc:
                result.fail_count += 1
                result.errors.append(f"DB insert failed for {file_path}: {exc}")
                continue

            # Write to vector store.
            text_content = _read_text_content(file_path)
            if text_content:
                vector_id = vs.add_embedding(
                    doc_id=doc_id,
                    text=text_content,
                    metadata={
                        "type": doc.type,
                        "title": doc.title,
                        "brand_id": brand,
                        "file_path": str(file_path),
                    },
                )
                if vector_id:
                    # Store the vector_id back into the DB row.
                    db.conn.execute(
                        "UPDATE assets SET vector_id = ? WHERE doc_id = ?",
                        (vector_id, doc_id),
                    )
                    db.conn.commit()

            result.success_count += 1
            logger.info("Ingested: %s (%s)", file_path.name, doc.type)

    finally:
        db.close()

    return result


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

_DECISION_SUBDIRS = {"decision", "research_data", "01_content", "02_images"}
_PROJECT_FILE_PATTERNS = ("*.md", "*.yaml", "*.yml", "*.json")


def _discover_artifacts(
    root: Path,
) -> list[tuple[Path, dict[str, Any]]]:
    """Walk *root* and return (file_path, hint_dict) pairs.

    Hints include the inferred type, source phase, and language
    based on the file's path and name.
    """
    artifacts: list[tuple[Path, dict[str, Any]]] = []
    seen: set[Path] = set()

    # 1. Walk known sub-directories.
    for subdir_name in _DECISION_SUBDIRS:
        subdir = root / subdir_name
        if subdir.is_dir():
            for pattern in _PROJECT_FILE_PATTERNS:
                for fp in sorted(subdir.rglob(pattern)):
                    if fp not in seen and _is_ingestible(fp):
                        seen.add(fp)
                        hints = _classify_by_path(fp, root)
                        artifacts.append((fp, hints))

    # 2. Top-level markdown / yaml / json files.
    for pattern in _PROJECT_FILE_PATTERNS:
        for fp in sorted(root.glob(pattern)):
            if fp not in seen and _is_ingestible(fp):
                seen.add(fp)
                hints = _classify_by_path(fp, root)
                artifacts.append((fp, hints))

    return artifacts


def _is_ingestible(fp: Path) -> bool:
    """Return ``True`` if the file looks like an ingestible artifact."""
    if fp.suffix.lower() not in _INGESTIBLE_EXTENSIONS:
        return False
    # Skip hidden files.
    if fp.name.startswith("."):
        return False
    # Skip files that are clearly not artifacts (e.g. project metadata).
    return fp.name not in ("00_project_info.json",)


def _classify_by_path(fp: Path, root: Path) -> dict[str, Any]:
    """Infer metadata from the file's relative path and name.

    Returns a dict with optional keys: ``type``, ``phase``, ``lang``.
    """
    hints: dict[str, Any] = {}
    rel = fp.relative_to(root)
    parts = rel.parts
    name_lower = fp.stem.lower()

    # 1. Detect type from directory or filename keywords.
    for keyword, atype in _PATH_TYPE_HINTS.items():
        if keyword in name_lower:
            hints["type"] = atype
            break
    if "type" not in hints:
        for part in parts:
            for keyword, atype in _PATH_TYPE_HINTS.items():
                if keyword in part.lower():
                    hints["type"] = atype
                    break
            if "type" in hints:
                break
    if "type" not in hints:
        hints["type"] = "content"  # fallback

    # 2. Detect source phase from directory structure.
    phase_hints = {
        "decision": "1b",
        "research_data": "1b",
        "01_content": "2",
        "02_images": "2",
        "03_video": "2",
        "04_subtitle": "2",
        "05_review": "3",
        "06_publish": "3",
        "phase-0": "0",
        "phase-1a": "1a",
        "phase-1b": "1b",
        "phase-1s": "1s",
        "phase-2": "2",
        "phase-3": "3",
    }
    for part in parts:
        for keyword, phase in phase_hints.items():
            if keyword in part.lower():
                hints["phase"] = phase
                break
        if "phase" in hints:
            break

    return hints


# ---------------------------------------------------------------------------
# AssetDoc builder
# ---------------------------------------------------------------------------


def _build_asset_doc(
    file_path: Path,
    brand: str,
    hints: dict[str, Any],
) -> AssetDoc:
    """Construct an ``AssetDoc`` from a file path and classification hints.

    Reads the file content to extract the title (from front-matter or
    filename), compute the MD5 checksum, and gather tags.
    """
    content_bytes = file_path.read_bytes()
    checksum = hashlib.md5(content_bytes).hexdigest()  # noqa: S324 — integrity checksum

    # Try to extract title from front-matter or first heading.
    title = _extract_title(file_path, content_bytes) or file_path.stem

    # Extract tags from front-matter (JSON or YAML).
    tags = _extract_tags(file_path, content_bytes)

    # Determine language from filename suffix (e.g. ``_zh.md``, ``_en.yaml``)
    lang = _detect_language(file_path.stem)

    asset_type = hints.get("type", "content")
    if asset_type not in ASSET_TYPES:
        asset_type = "content"

    return AssetDoc(
        brand_id=brand,
        type=asset_type,
        source_phase=hints.get("phase", ""),
        title=title,
        tags=tags,
        lang=lang,
        file_path=str(file_path.resolve()),
        source_project_id=file_path.parent.name,
        checksum=checksum,
    )


# ---------------------------------------------------------------------------
# Text / metadata extraction helpers
# ---------------------------------------------------------------------------

_FRONT_MATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _read_text_content(file_path: Path) -> str:
    """Read the textual content of a file for embedding.

    Strips YAML/JSON front-matter for cleaner embedding input.
    """
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    # Strip front-matter.
    raw = _FRONT_MATTER_RE.sub("", raw, count=1)
    return raw.strip()


def _extract_title(
    file_path: Path,
    content_bytes: bytes,
) -> str | None:
    """Extract a human-readable title from the file content.

    Priority:
    1. ``title`` field in YAML/JSON front-matter
    2. First Markdown heading (``# `` or ``## ``)
    3. ``name`` key in JSON content
    4. ``None`` (caller falls back to filename stem)
    """
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None

    # 1. Front-matter title.
    m = _FRONT_MATTER_RE.match(text)
    if m:
        fm_text = m.group(1)
        # Try JSON front-matter.
        try:
            fm = json.loads(fm_text)
            if isinstance(fm, dict) and fm.get("title"):
                return str(fm["title"]).strip()
        except json.JSONDecodeError:
            pass
        # Try simple key: value lines (YAML-like).
        title_match = re.search(
            r'^title\s*:\s*["\']?(.+?)["\']?\s*$',
            fm_text,
            re.MULTILINE,
        )
        if title_match:
            return title_match.group(1).strip()

    # 2. First Markdown heading.
    heading = re.search(r"^#{1,2}\s+(.+)$", text, re.MULTILINE)
    if heading:
        return heading.group(1).strip()

    # 3. Try parsing the whole file as JSON.
    if file_path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                for key in ("title", "name", "topic"):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except json.JSONDecodeError:
            pass

    return None


def _extract_tags(
    file_path: Path,
    content_bytes: bytes,
) -> list[str]:
    """Extract tags from the file's front-matter or content.

    Tags supplement the built-in type taxonomy and are stored as a
    JSON array in the ``tags`` column.
    """
    tags: list[str] = []
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return tags

    # 1. Front-matter tags.
    m = _FRONT_MATTER_RE.match(text)
    if m:
        fm_text = m.group(1)
        try:
            fm = json.loads(fm_text)
            if isinstance(fm, dict):
                raw_tags = fm.get("tags", fm.get("keywords", []))
                if isinstance(raw_tags, list):
                    tags.extend(str(t) for t in raw_tags)
        except json.JSONDecodeError:
            pass

        # Also try YAML-style tags line.
        if not tags:
            yaml_tags = re.search(
                r"^tags\s*:\s*\[(.+?)\]\s*$",
                fm_text,
                re.MULTILINE,
            )
            if yaml_tags:
                raw = yaml_tags.group(1)
                tags.extend(t.strip().strip("\"'") for t in raw.split(",") if t.strip())

    # 2. Add file extension as an automatic tag.
    ext = file_path.suffix.lower().lstrip(".")
    if ext:
        tags.append(f"format:{ext}")

    # 3. Deduplicate preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for t in tags:
        t_lower = t.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            deduped.append(t)
    return deduped


def _detect_language(stem: str) -> str:
    """Detect language from filename suffix patterns.

    Examples
    --------
    >>> _detect_language("brief_zh")
    'zh'
    >>> _detect_language("brief_en")
    'en'
    >>> _detect_language("brief")
    'zh'
    """
    match = re.search(r"_([a-z]{2}(?:-[A-Z]{2})?)$", stem)
    if match:
        return match.group(1)
    return "zh"
