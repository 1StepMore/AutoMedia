"""Compatibility scanner — verify new Project system recognises historical layouts.

Scans historical Hermes project structures from
``automedia-package/03_项目文档/PROJECT_REGISTRY.json`` and reports whether
each project can be represented by the new ``automedia.core.project.Project``
dataclass schema.

Usage::

    from automedia.core.compat_scanner import scan_all, generate_report

    results = scan_all(registry_path)
    report  = generate_report(results)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# New-standard directory layout (mirrors project.Project.init)
# ---------------------------------------------------------------------------

_STANDARD_SUBDIRS: list[str] = [
    "01_content",
    "02_images",
    "03_video",
    "04_subtitle",
    "05_review",
    "06_publish",
]

# Fields that map 1-to-1 from historical info → new Project schema
_MAPPED_FIELDS: set[str] = {"project_id", "topic", "created_at"}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class CompatResult:
    """Result of scanning a single historical project directory.

    Attributes
    ----------
    project_id:
        The project identifier extracted from the info file.
    path:
        Absolute path to the project directory.
    info_format:
        ``"a"`` (flat), ``"b"`` (nested), or ``None``.
    field_mapping:
        Dict produced by :func:`map_fields` (includes ``historical_only``).
    asset_paths:
        Dict with ``video_paths`` and ``publish_paths`` lists.
    dir_structure:
        Dict with ``present`` and ``missing`` subdirectory lists.
    compatible:
        ``True`` when the project has all required mapped fields and no
        parse errors.
    errors:
        List of error/warning strings.
    """

    project_id: str | None = None
    path: str = ""
    info_format: str | None = None
    field_mapping: dict[str, Any] = field(default_factory=dict)
    asset_paths: dict[str, list[str]] = field(default_factory=dict)
    dir_structure: dict[str, list[str]] = field(default_factory=dict)
    compatible: bool = False
    errors: list[str] = field(default_factory=list)

    # -- dict-like access for backward compat with test assertions --------
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style ``.get()`` accessor."""
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


def load_registry(path: str | Path) -> list[dict[str, Any]]:
    """Parse ``PROJECT_REGISTRY.json`` and return a flat list of records.

    Combines records from ``active``, ``orphans``, and ``archived`` keys.

    Parameters
    ----------
    path:
        Path to the registry JSON file.

    Returns
    -------
    list[dict]
        Merged list of project record dicts.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Registry file not found: {p}")

    data = json.loads(p.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for key in ("active", "orphans", "archived"):
        records.extend(data.get(key, []))
    return records


# ---------------------------------------------------------------------------
# Info-file detection & parsing
# ---------------------------------------------------------------------------


def detect_info_format(project_dir: str | Path) -> str | None:
    """Detect the layout form of the project-info file.

    Returns
    -------
    str or None
        ``"a"`` if ``00_project_info.json`` exists at project root,
        ``"b"`` if ``00_project_info/project_info.json`` exists,
        ``None`` when no info file is found.
    """
    p = Path(project_dir)
    if (p / "00_project_info.json").is_file():
        return "a"
    if (p / "00_project_info" / "project_info.json").is_file():
        return "b"
    return None


def parse_historical_info(project_dir: str | Path) -> dict[str, Any]:
    """Read and return the info dict from a historical project directory.

    Supports both Form A (flat) and Form B (nested) layouts.

    Parameters
    ----------
    project_dir:
        Path to the project directory.

    Returns
    -------
    dict
        Parsed info dictionary.

    Raises
    ------
    FileNotFoundError
        If no info file is found.
    json.JSONDecodeError
        If the info file contains invalid JSON.
    """
    p = Path(project_dir)
    fmt = detect_info_format(p)

    if fmt == "a":
        info_path = p / "00_project_info.json"
    elif fmt == "b":
        info_path = p / "00_project_info" / "project_info.json"
    else:
        raise FileNotFoundError(f"No project info file found in {p}")

    with open(info_path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


def map_fields(info: dict[str, Any]) -> dict[str, Any]:
    """Map historical info fields to the new Project schema.

    Fields that exist in both schemas are placed at the top level.
    Fields unique to the historical schema are grouped under
    ``historical_only``.  New-schema fields absent from the historical
    record receive sensible defaults (``brand=""``, ``tenant_id="default"``).

    Parameters
    ----------
    info:
        Parsed historical info dict.

    Returns
    -------
    dict
        Mapping with top-level keys ``project_id``, ``topic``,
        ``created_at``, ``brand``, ``tenant_id``, and ``historical_only``.
    """
    result: dict[str, Any] = {}
    historical_only: dict[str, Any] = {}

    for key, value in info.items():
        if key in _MAPPED_FIELDS:
            result[key] = value
        else:
            historical_only[key] = value

    # Defaults for new-schema fields absent from historical records
    result["brand"] = info.get("brand", "")
    result["tenant_id"] = info.get("tenant_id", "default")
    result["historical_only"] = historical_only

    return result


# ---------------------------------------------------------------------------
# Asset-path detection
# ---------------------------------------------------------------------------


def check_asset_paths(project_dir: str | Path) -> dict[str, list[str]]:
    """Detect recognised media-asset paths in a project directory.

    Scans ``03_video/`` and ``05_publish/`` for files.

    Parameters
    ----------
    project_dir:
        Path to the project directory.

    Returns
    -------
    dict
        ``{"video_paths": [...], "publish_paths": [...]}`` with
        relative paths (e.g. ``"03_video/video_final.mp4"``).
    """
    p = Path(project_dir)
    video_paths: list[str] = []
    publish_paths: list[str] = []

    video_dir = p / "03_video"
    if video_dir.is_dir():
        for item in sorted(video_dir.iterdir()):
            if item.is_file():
                video_paths.append(f"03_video/{item.name}")

    publish_dir = p / "05_publish"
    if publish_dir.is_dir():
        for item in sorted(publish_dir.iterdir()):
            if item.is_file():
                publish_paths.append(f"05_publish/{item.name}")

    return {"video_paths": video_paths, "publish_paths": publish_paths}


# ---------------------------------------------------------------------------
# Directory-structure check
# ---------------------------------------------------------------------------


def check_dir_structure(project_dir: str | Path) -> dict[str, list[str]]:
    """Compare actual subdirectories against the new standard layout.

    Parameters
    ----------
    project_dir:
        Path to the project directory.

    Returns
    -------
    dict
        ``{"present": [...], "missing": [...]}`` where *present* lists
        actual subdirectory names and *missing* lists standard dirs that
        are absent.
    """
    p = Path(project_dir)
    present: list[str] = []

    if p.is_dir():
        for item in sorted(p.iterdir()):
            if item.is_dir():
                present.append(item.name)

    missing = [d for d in _STANDARD_SUBDIRS if d not in present]
    return {"present": present, "missing": missing}


# ---------------------------------------------------------------------------
# Project scanning
# ---------------------------------------------------------------------------


def scan_project(project_dir: str | Path) -> CompatResult:
    """Run a full compatibility scan on a single project directory.

    Parameters
    ----------
    project_dir:
        Path to the project directory.

    Returns
    -------
    CompatResult
        Scan result with ``compatible``, ``errors``, etc.
    """
    p = Path(project_dir)
    result = CompatResult(path=str(p))

    # 1. Detect format
    fmt = detect_info_format(p)
    result.info_format = fmt

    if fmt is None:
        result.errors.append("No project info file found")
        return result

    # 2. Parse info (may raise JSONDecodeError)
    try:
        info = parse_historical_info(p)
    except json.JSONDecodeError as exc:
        result.errors.append(f"JSON parse error: {exc}")
        return result

    result.project_id = info.get("project_id")

    # 3. Map fields
    result.field_mapping = map_fields(info)

    # 4. Asset paths
    result.asset_paths = check_asset_paths(p)

    # 5. Directory structure
    result.dir_structure = check_dir_structure(p)

    # 6. Compatibility — all three required mapped fields must be truthy
    required = ("project_id", "topic", "created_at")
    has_required = all(info.get(f) for f in required)
    result.compatible = has_required and not result.errors

    return result


def scan_all(project_dirs: list[str | Path]) -> list[CompatResult]:
    """Scan multiple project directories.

    Parameters
    ----------
    project_dirs:
        List of project directory paths.

    Returns
    -------
    list[CompatResult]
        One result per directory, in order.
    """
    return [scan_project(d) for d in project_dirs]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    scan_results: list[CompatResult],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a compatibility report from scan results.

    Parameters
    ----------
    scan_results:
        List of :class:`CompatResult` instances (or dicts).
    output_path:
        When provided, the report is also written as JSON to this path.

    Returns
    -------
    dict
        Report with keys ``generated_at``, ``total_projects``,
        ``compatible``, ``incompatible``, ``field_mapping``,
        ``directory_mapping``, ``details``.
    """
    total = len(scan_results)
    compatible_count = sum(1 for r in scan_results if r.get("compatible"))

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_projects": total,
        "compatible": compatible_count,
        "incompatible": total - compatible_count,
        "field_mapping": {
            "project_id": "project_id",
            "topic": "topic",
            "created_at": "created_at",
        },
        "directory_mapping": {
            old: new
            for old, new in zip(
                ["00_project_info", "01_content", "02_images", "03_video",
                 "04_subtitle", "05_publish", "05_review", "06_publish"],
                _STANDARD_SUBDIRS,
            )
        },
        "details": [
            {
                "project_id": r.get("project_id"),
                "compatible": bool(r.get("compatible")),
            }
            for r in scan_results
        ],
    }

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return report
