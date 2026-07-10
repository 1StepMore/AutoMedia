"""AutoMedia MCP Server — stdio transport with 12 tools.

Provides an MCP-compliant server exposing AutoMedia pipeline operations
as LLM-callable tools.  All file-system operations are gated behind a
path allowlist loaded from ``mcp_allowlist.yaml``.

.. note::

   **Dual-allowlist architecture:** This module implements the *MCP server*
   allowlist (``mcp_allowlist.yaml`` — ``allowed_directories`` schema).
   There is a separate *Omni adapter* allowlist at ``~/.automedia/omni_allowlist.yaml``
   (``allowed_paths`` / ``write_paths`` schema) consumed by
   :mod:`automedia.omni.allowlist`.  The two serve different layers — MCP
   file-access gating vs. Omni adapter file operations — and should not be
   confused.

Usage::

    # Install with the ``mcp`` extra
    pip install -e ".[mcp]"

    # Run the server (stdio transport)
    python3 -m automedia.mcp.server

    # Or show help
    python3 -m automedia.mcp.server --help
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import yaml

# ---------------------------------------------------------------------------
# Allowlist helpers
# ---------------------------------------------------------------------------

_ALLOWLIST_FILE = Path(__file__).parent / "mcp_allowlist.yaml"

# Cache the resolved allowlist directories so we don't re-read YAML on every
# tool call.  Populated by ``_load_allowlist()`` on first access.
_cached_allowlist: list[str] | None = None


def _load_allowlist(*, allowlist_path: Path | None = None) -> list[str]:
    """Load and cache allowed directories from the YAML config.

    Parameters
    ----------
    allowlist_path:
        Override path to the allowlist YAML file.  When *None* the
        default ``mcp_allowlist.yaml`` next to this module is used.

    Returns
    -------
    list[str]
        Resolved absolute directory paths.
    """
    global _cached_allowlist
    path = allowlist_path if allowlist_path is not None else _ALLOWLIST_FILE
    if not path.exists():
        _cached_allowlist = []
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw: list[str] = data.get("allowed_directories", []) or []
    resolved = [os.path.realpath(os.path.expanduser(d)) for d in raw]
    _cached_allowlist = resolved
    return resolved


def _reset_allowlist_cache() -> None:
    """Reset the cached allowlist.  Used in tests."""
    global _cached_allowlist
    _cached_allowlist = None


def check_path_allowed(path: str, *, allowlist: list[str] | None = None) -> bool:
    """Return *True* if *path* falls under an allowed directory.

    When the allowlist is empty **all paths are blocked** (fail‑closed).

    Parameters
    ----------
    path:
        File or directory path to validate (need not exist).
    allowlist:
        Override list of resolved directory paths.  When *None* the
        cached allowlist from the YAML file is used.
    """
    if allowlist is None:
        allowlist = _cached_allowlist if _cached_allowlist is not None else _load_allowlist()
    if not allowlist:
        return False  # fail‑closed: empty allowlist → deny all
    from pathlib import Path
    real = Path(path).resolve()
    for d in allowlist:
        try:
            real.relative_to(Path(d).resolve())
            return True
        except ValueError:
            continue
    return False


def _require_allowed(path: str, *, tool_name: str = "") -> None:
    """Raise ``ValueError`` if *path* is not in the allowlist."""
    if not check_path_allowed(path):
        prefix = f"[{tool_name}] " if tool_name else ""
        raise ValueError(
            f"{prefix}Path {path!r} is not within any allowed directory. "
            f"Configure allowed_directories in mcp_allowlist.yaml."
        )


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _discover_projects(base_dir: str) -> list[dict[str, Any]]:
    """Scan *base_dir* for project info JSON files and return their contents."""
    projects: list[dict[str, Any]] = []
    base = Path(base_dir)
    for info_file in sorted(base.glob("*/00_project_info.json")):
        try:
            with open(info_file, encoding="utf-8") as fh:
                data = json.load(fh)
            data["_dir"] = str(info_file.parent)
            projects.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return projects


def _project_assets(project_dir: str) -> list[dict[str, Any]]:
    """Walk *project_dir* and return a list of asset metadata dicts."""
    assets: list[dict[str, Any]] = []
    root = Path(project_dir)
    if not root.is_dir():
        return assets
    for fpath in sorted(root.rglob("*")):
        if fpath.is_file() and fpath.name != "00_project_info.json":
            rel = fpath.relative_to(root)
            assets.append({
                "path": str(fpath),
                "relative_path": str(rel),
                "name": fpath.name,
                "size_bytes": fpath.stat().st_size,
            })
    return assets


def _pipeline_result_to_dict(result: Any) -> dict[str, Any]:
    """Convert a :class:`PipelineResult` dataclass to a plain dict."""
    from dataclasses import asdict

    try:
        return asdict(result)
    except Exception:
        # Fallback: manual extraction
        return {
            "status": getattr(result, "status", "unknown"),
            "project_id": getattr(result, "project_id", ""),
            "project_dir": getattr(result, "project_dir", ""),
            "topic": getattr(result, "topic", ""),
            "brand": getattr(result, "brand", ""),
            "error": getattr(result, "error", None),
        }


# ---------------------------------------------------------------------------
# Pipeline progress tracker
# ---------------------------------------------------------------------------

from automedia.pipelines.gate_engine import PipelineProgress

# Global tracker: project_id → PipelineProgress for agent polling.
# Thread-safe via _lock (background pipeline thread vs. MCP query thread).
_pipeline_tracker: dict[str, PipelineProgress] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Tool handler functions (module-level for testability)
# ---------------------------------------------------------------------------

def select_topic(
    category: str = "",
    tenant_id: str = "default",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """Select the highest-scored pending topic from the pool.

    Parameters
    ----------
    category:
        Optional category filter (e.g. ``"tech"``, ``"finance"``).
    tenant_id:
        Tenant / namespace identifier.
    pool_db_path:
        Explicit path to the topic pool SQLite database.  When
        empty the default location is used.

    Returns
    -------
    dict
        ``{"selected": {...}, "remaining_count": int}`` or
        ``{"selected": null, "error": str}``.
    """
    try:
        from automedia.pool.db import PoolDB

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="select_topic")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(":memory:")

        topics = db.list_topics(status="pending")
        if category:
            topics = [t for t in topics if t.get("category") == category]
        if tenant_id and tenant_id != "default":
            topics = [t for t in topics if t.get("tenant_id") == tenant_id]

        if not topics:
            return {"selected": None, "remaining_count": 0, "error": "No pending topics found"}

        # Sort by score descending
        topics.sort(key=lambda t: t.get("score", 0.0), reverse=True)
        chosen = topics[0]
        db.mark_selected(chosen["id"])
        db.close()
        return {"selected": chosen, "remaining_count": len(topics) - 1}

    except Exception as exc:
        return {"selected": None, "error": str(exc)}


def run_pipeline(
    topic: str,
    brand: str,
    mode: str = "auto",
    tenant_id: str = "default",
    resume_from: str = "",
) -> dict[str, Any]:
    """Execute the full AutoMedia production pipeline in a background thread.

    Launches the pipeline asynchronously and returns immediately with a
    ``project_id`` that can be used with ``get_pipeline_progress`` to
    poll execution status.

    Parameters
    ----------
    topic:
        Content topic / subject.
    brand:
        Brand identifier.
    mode:
        Pipeline mode — ``"auto"``, ``"text_only"``, ``"video_only"``,
        or ``"qa_only"``.
    tenant_id:
        Tenant / namespace identifier.
    resume_from:
        Gate name to resume from (skip preceding gates).  Empty
        runs from the beginning.

    Returns
    -------
    dict
        ``{"project_id": str, "status": "started"}`` on success, or
        ``{"status": "failed", "error": str}`` on immediate failure.
    """
    # Pre-validate mode to fail fast
    VALID_MODES = ("auto", "text_only", "video_only", "qa_only")
    if mode not in VALID_MODES:
        return {
            "status": "failed",
            "error": f"Unknown pipeline mode {mode!r}. Choose from: {list(VALID_MODES)}",
        }

    project_id = str(uuid.uuid4())[:12]
    progress = PipelineProgress(project_id=project_id)
    with _lock:
        _pipeline_tracker[project_id] = progress

    def _run() -> None:
        """Background thread — wraps pipeline execution in try/except."""
        try:
            from automedia.pipelines.runner import run_full_pipeline

            result = run_full_pipeline(
                topic=topic,
                brand=brand,
                mode=mode,
                tenant_id=tenant_id,
                resume_from=resume_from or None,
            )
            progress.project_id = result.project_id
        except Exception as exc:
            progress.error = str(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"project_id": project_id, "status": "started"}


def get_pipeline_progress(project_id: str) -> dict[str, Any]:
    """Get current progress of a running pipeline by project_id.

    Poll this after ``run_pipeline`` to observe gate execution in real
    time.  Returns the current gate, a list of gate progress events
    (start / passed / failed), and any error captured from the background
    thread.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.

    Returns
    -------
    dict
        ``{"project_id", "current_gate", "events", "error"}`` or
        ``{"error": "not found"}``.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return {"error": f"No active pipeline found for project_id {project_id!r}"}
    return progress.get_progress()


def get_pipeline_status(
    project_id: str,
    base_dir: str = ".",
) -> dict[str, Any]:
    """Return the current status / progress of a pipeline run.

    Looks up the project by *project_id* and returns its metadata
    together with the sub-directory listing as a proxy for progress.

    Parameters
    ----------
    project_id:
        The 12-char hex project identifier.
    base_dir:
        Base directory to scan for projects.

    Returns
    -------
    dict
        ``{"project": {...}, "subdirs": [...]}`` or error.
    """
    try:
        _require_allowed(base_dir, tool_name="get_pipeline_status")
        projects = _discover_projects(base_dir)
        match = [p for p in projects if p.get("project_id") == project_id]
        if not match:
            return {"error": f"Project {project_id!r} not found"}
        proj = match[0]
        proj_dir = proj.get("_dir", "")
        subdirs = []
        if proj_dir and Path(proj_dir).is_dir():
            subdirs = sorted(
                str(p.relative_to(proj_dir))
                for p in Path(proj_dir).iterdir()
                if p.is_dir()
            )
        return {"project": proj, "subdirs": subdirs}

    except Exception as exc:
        return {"error": str(exc)}


def list_projects(
    base_dir: str = ".",
    status: str = "",
) -> dict[str, Any]:
    """List all projects found under *base_dir*.

    Parameters
    ----------
    base_dir:
        Root directory to scan for ``00_project_info.json`` files.
    status:
        Optional status filter (e.g. ``"published"``).

    Returns
    -------
    dict
        ``{"projects": [...]}``.
    """
    try:
        _require_allowed(base_dir, tool_name="list_projects")
        projects = _discover_projects(base_dir)
        if status:
            projects = [p for p in projects if p.get("status", "") == status]
        return {"projects": projects, "count": len(projects)}

    except Exception as exc:
        return {"projects": [], "error": str(exc)}


def get_project_assets(
    project_dir: str,
) -> dict[str, Any]:
    """Return the list of asset files inside a project directory.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root.

    Returns
    -------
    dict
        ``{"assets": [...], "count": int}``.
    """
    try:
        _require_allowed(project_dir, tool_name="get_project_assets")
        assets = _project_assets(project_dir)
        return {"assets": assets, "count": len(assets)}

    except Exception as exc:
        return {"assets": [], "error": str(exc)}


def archive_project(
    project_id: str,
    base_dir: str = ".",
    force: bool = False,
) -> dict[str, Any]:
    """Archive a project (Red Line 8 enforcement).

    Refuses to archive unless the project status is ``"published"``
    or *force* is ``True``.

    Parameters
    ----------
    project_id:
        The 12-char hex project identifier.
    base_dir:
        Base directory to scan for projects.
    force:
        Force archive even if status is not ``"published"``.

    Returns
    -------
    dict
        ``{"archived": True, "archive_dir": str}`` or error.
    """
    try:
        _require_allowed(base_dir, tool_name="archive_project")

        # Red Line 8: refuse without force when status ≠ published
        projects = _discover_projects(base_dir)
        match = [p for p in projects if p.get("project_id") == project_id]
        if not match:
            return {"archived": False, "error": f"Project {project_id!r} not found"}

        proj = match[0]
        status_val = str(proj.get("status", ""))
        if status_val != "published" and not force:
            return {
                "archived": False,
                "error": (
                    f"Refused: project status is '{status_val}', not 'published'. "
                    f"Set force=True to override (Red Line 8)."
                ),
            }

        project_dir = Path(proj["_dir"])
        archive_dir = project_dir.parent / f"{project_dir.name}_archived"
        if archive_dir.exists():
            return {"archived": False, "error": f"Archive target already exists: {archive_dir}"}

        project_dir.rename(archive_dir)
        return {"archived": True, "archive_dir": str(archive_dir)}

    except Exception as exc:
        return {"archived": False, "error": str(exc)}


def list_topic_pool(
    status: str = "",
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """List topics in the pool, optionally filtered by status or category.

    Parameters
    ----------
    status:
        Filter by topic status (e.g. ``"pending"``, ``"selected"``).
    category:
        Filter by category.
    pool_db_path:
        Explicit path to the topic pool SQLite database.

    Returns
    -------
    dict
        ``{"topics": [...], "count": int}``.
    """
    try:
        from automedia.pool.db import PoolDB

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="list_topic_pool")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(":memory:")

        topics = db.list_topics(status=status or None)
        if category:
            topics = [t for t in topics if t.get("category") == category]
        db.close()
        return {"topics": topics, "count": len(topics)}

    except Exception as exc:
        return {"topics": [], "error": str(exc)}


def register_platform_adapter(
    platform_name: str,
    adapter_class: str = "",
) -> dict[str, Any]:
    """Register a platform adapter (stub — PRD-1 NG6).

    ------------------------------------------------------------------
    ╔══════════════════════════════════════════════════════════════════╗
    ║  STUB NOTICE: Per PRD-1 NG6, no new content production          ║
    ║  platforms are added in this phase.  This function serves as    ║
    ║  a **validated placeholder** that records the intent to         ║
    ║  register an adapter, but does *not* wire up real platform      ║
    ║  connectivity.                                                  ║
    ║                                                                ║
    ║  Future implementation path:                                     ║
    ║  1. Create a concrete adapter class in a new module under        ║
    ║     ``automedia/adapters/`` (e.g. ``wechat.py``).               ║
    ║  2. The class should inherit from a base adapter protocol        ║
    ║     (defined elsewhere) and implement ``publish()``.             ║
    ║  3. Call this function with the dotted path to that class.       ║
    ║  4. The dynamic import below will register it with               ║
    ║     ``AdapterRegistry`` for downstream use.                     ║
    ╚══════════════════════════════════════════════════════════════════╝
    ------------------------------------------------------------------

    Parameters
    ----------
    platform_name:
        Platform identifier (e.g. ``"wechat"``, ``"weibo"``).
        Must be non-empty and match ``[a-zA-Z0-9_-]+``.
    adapter_class:
        Dotted Python path to the adapter class (e.g.
        ``"automedia.adapters.wechat.WeChatAdapter"``).
        When empty the function acts as a pure stub.

    Returns
    -------
    dict
        With ``adapter_class``: ``{"registered": True, "platform": str,
        "class": str}`` on success.
        Without ``adapter_class``: ``{"registered": False, "stub": True,
        "platform": str, "message": str, "instructions": str}``.
        On error: ``{"registered": False, "error": str}``.
    """
    import re

    if not platform_name or not isinstance(platform_name, str):
        return {
            "registered": False,
            "error": "platform_name must be a non-empty string.",
        }
    if not re.match(r"^[a-zA-Z0-9_-]+$", platform_name):
        return {
            "registered": False,
            "error": (
                f"Invalid platform_name {platform_name!r}. "
                f"Use only letters, digits, underscores, and hyphens."
            ),
        }

    try:
        from automedia.adapters.registry import AdapterRegistry

        if adapter_class:
            module_path, _, class_name = adapter_class.rpartition(".")
            if not module_path:
                return {
                    "registered": False,
                    "error": (
                        f"Invalid adapter_class {adapter_class!r}: "
                        f"must be a dotted path (e.g. 'pkg.mod.ClassName')."
                    ),
                }
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            AdapterRegistry.register(cls)
            return {"registered": True, "platform": platform_name, "class": adapter_class}

        return {
            "registered": False,
            "platform": platform_name,
            "stub": True,
            "message": (
                f"Stub: adapter for {platform_name!r} acknowledged. "
                f"Provide a dotted ``adapter_class`` path to fully register."
            ),
            "instructions": (
                f"To implement the {platform_name!r} adapter:\n"
                f"  1. Create automedia/adapters/{platform_name}.py with a class\n"
                f"     that implements the adapter protocol.\n"
                f"  2. Call register_platform_adapter(\n"
                f"       platform_name={platform_name!r},\n"
                f"       adapter_class='automedia.adapters.{platform_name}.<ClassName>',\n"
                f"     )\n"
                f"  3. The adapter will be registered with AdapterRegistry."
            ),
        }

    except Exception as exc:
        return {"registered": False, "error": str(exc)}


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
        return {
            "md_content": result.md_content,
            "manifest_json": result.manifest,
            "warnings": result.warnings,
        }
    except Exception as exc:
        return {"md_content": "", "manifest_json": {}, "warnings": [str(exc)]}


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
        return {
            "translated_md": result.translated_md,
            "xliff_path": result.xliff_path,
            "warnings": result.warnings,
        }
    except Exception as exc:
        return {"translated_md": "", "xliff_path": None, "warnings": [str(exc)]}


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
        from automedia.omni.ol_adapter import OLAdapter
        from pathlib import Path

        proj = Path(project_dir)
        drafts_dir = proj / "01_content" / "drafts"

        results: dict[str, list[str]] = {}
        warnings: list[str] = []

        if not drafts_dir.is_dir():
            return {
                "project_dir": project_dir,
                "results": results,
                "warnings": [f"Drafts directory not found: {drafts_dir}"],
            }

        langs = [l.strip() for l in target_langs.split(",") if l.strip()]
        if not langs:
            return {
                "project_dir": project_dir,
                "results": results,
                "warnings": ["No target languages specified"],
            }

        md_files = sorted(drafts_dir.glob("*.md"))
        if not md_files:
            return {
                "project_dir": project_dir,
                "results": results,
                "warnings": [f"No markdown files found in {drafts_dir}"],
            }

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
                    warnings.append(
                        f"Translation failed for {md_file.name} → {lang}: {exc}"
                    )

        return {
            "project_dir": project_dir,
            "results": results,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
        }


def format_output(
    content: str,
    target_format: str,
    **options: Any,
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
        return {
            "output_path": output_path,
            "output_format": target_format,
            "warnings": errors if errors else [],
        }
    except Exception as exc:
        return {"output_path": "", "output_format": target_format, "warnings": [str(exc)]}
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.warning("Failed to clean up temp file %s", temp_path)


# ---------------------------------------------------------------------------
# MCP Server construction
# ---------------------------------------------------------------------------

def create_server() -> Any:
    """Create and configure the FastMCP server instance.

    Returns
    -------
    FastMCP
        A fully configured server with all 13 tools registered.
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="AutoMedia",
        instructions=(
            "AutoMedia automated media production pipeline. "
            "Use these tools to manage topic pools, run production pipelines, "
            "and inspect project assets."
        ),
    )

    # Register all 12 tools
    mcp.tool(
        description=(
            "Select the highest-scored pending topic from the pool. "
            "Returns the selected topic and remaining count."
        ),
    )(select_topic)

    mcp.tool(
        description=(
            "Execute the full AutoMedia production pipeline. "
            "Returns PipelineResult as JSON."
        ),
    )(run_pipeline)

    mcp.tool(
        description=(
            "Get the current progress of a running pipeline by project_id. "
            "Returns the current gate, all gate progress events (start / "
            "passed / failed), and any errors captured from the background "
            "thread. Poll this after run_pipeline to observe execution."
        ),
    )(get_pipeline_progress)

    mcp.tool(
        description=(
            "Return the current status / progress of a pipeline run "
            "by project ID."
        ),
    )(get_pipeline_status)

    mcp.tool(
        description=(
            "List all projects found under a base directory, "
            "optionally filtered by status."
        ),
    )(list_projects)

    mcp.tool(
        description=(
            "Return the list of asset files inside a project directory."
        ),
    )(get_project_assets)

    mcp.tool(
        description=(
            "Archive a project. Red Line 8: refuses unless status is "
            "'published' or force=True."
        ),
    )(archive_project)

    mcp.tool(
        description=(
            "List topics in the pool, optionally filtered by "
            "status or category."
        ),
    )(list_topic_pool)

    mcp.tool(
        description=(
            "Register a platform adapter (stub). Provide platform_name "
            "and optional adapter_class dotted path."
        ),
    )(register_platform_adapter)

    # ------------------------------------------------------------------
    # Omni tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Extract a content brief from a document file using OPP. "
            "Processes the document through OPPAdapter.extract() and "
            "returns structured markdown content, a manifest JSON with "
            "segment metadata, and any warnings encountered."
        ),
    )(extract_brief)

    mcp.tool(
        description=(
            "Translate markdown content from source to target language. "
            "Delegates to OLAdapter.translate() which uses the OL shield "
            "→ LLM-translate → repair → unshield pipeline. Returns the "
            "translated markdown, optional XLIFF path, and warnings."
        ),
    )(localize_content)

    mcp.tool(
        description=(
            "Convert content to the specified output format. "
            "Delegates to ORFAdapter.convert() to transform content "
            "into the requested format. Returns the output path, "
            "format identifier, and any warnings or errors."
        ),
    )(format_output)

    mcp.tool(
        description=(
            "Translate all project drafts into multiple target languages. "
            "Reads markdown from 01_content/drafts/, translates via OLAdapter, "
            "writes translated files to 05_publish/{lang}/. "
            "Returns a mapping of language code to list of output file paths."
        ),
    )(localize_output)

    return mcp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the AutoMedia MCP server (stdio transport)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m automedia.mcp.server",
        description="AutoMedia MCP Server — stdio transport with 12 tools.",
    )
    parser.add_argument(
        "--show-tools",
        action="store_true",
        help="List registered tool names and exit.",
    )
    args = parser.parse_args()

    server = create_server()

    if args.show_tools:
        # FastMCP stores tools internally; print names for quick inspection
        print("Registered MCP tools:")
        for name in sorted(server._tool_manager._tools.keys()):
            print(f"  - {name}")
        return

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
