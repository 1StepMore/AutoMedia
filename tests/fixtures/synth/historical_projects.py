"""Synthetic historical project records and directories for W1-T32 compatibility testing.

Builders in this module create fixture data that mimics the old Hermes project
structure found in ``automedia-package/03_项目文档/PROJECT_REGISTRY.json``.

The compatibility scanner (``automedia/compat/``) must recognise these legacy
layouts and translate them into the new ``Project`` dataclass schema
(``project_id``, ``topic``, ``brand``, ``tenant_id``, ``created_at``).

Every builder returns synthetic data — zero production values are used.

Usage::

    from tests.fixtures.synth.historical_projects import (
        build_historical_record,
        build_historical_project_dir,
    )

    record = build_historical_record()
    directory = build_historical_project_dir(tmp_path)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants  (all synthetic)
# ---------------------------------------------------------------------------

_SYNTHETIC_TOPIC = "合成话题：AI 内容生产的新范式"
_SYNTHETIC_SLUG = "synthetic-ai-content-paradigm"
_SYNTHETIC_PROJECT_ID = "20260701_120000_synthetic-ai-content-paradigm"
_SYNTHETIC_TOPIC_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
_SYNTHETIC_CREATED_AT = "2026-07-01T12:00:00"
_SYNTHETIC_VIDEO_PATH = "03_video/video_final.mp4"
_SYNTHETIC_PUBLISH_LOG_PATH = "05_publish/publish_log.json"


# ---------------------------------------------------------------------------
# Record builder
# ---------------------------------------------------------------------------


def build_historical_record(
    *,
    project_id: str = _SYNTHETIC_PROJECT_ID,
    topic_id: str = _SYNTHETIC_TOPIC_ID,
    source: str = "manual",
    topic: str = _SYNTHETIC_TOPIC,
    topic_slug: str = _SYNTHETIC_SLUG,
    category: str = "业务款",
    angle: str = (
        "合成话题的角度描述——AI 内容生产工具正在改变行业格局，"
        "中小企业需要低成本高效率的解决方案。"
    ),
    bridge: str = (
        "工具进步不是新闻，怎么用工具规模化产出才是。"
        "壹目贯维把 AI 写稿、配图、发布串成全流程。"
    ),
    cta: str = (
        "关注壹目贯维，了解 AI 如何帮你把内容生产效率提升 10 倍。"
    ),
    keywords: list[str] | None = None,
    created_at: str = _SYNTHETIC_CREATED_AT,
    status: str = "initialized",
    include_angle: bool = True,
    include_bridge: bool = True,
    include_cta: bool = True,
    include_keywords: bool = True,
) -> dict[str, Any]:
    """Build a single synthetic historical project record.

    The returned dict mirrors the schema found in
    ``PROJECT_REGISTRY.json`` entries with keys ``id``, ``info``,
    ``publish_log``, and ``path``.

    Parameters
    ----------
    project_id:
        Unique project identifier (default synthetic).
    topic_id:
        MD5-like topic hash (default synthetic).
    source:
        Source type — ``"manual"`` or ``"pool"``.
    topic:
        Human-readable topic string.
    topic_slug:
        URL-safe slug derived from *topic*.
    category:
        Content category — ``"引流款"``, ``"业务款"``, etc.
    angle, bridge, cta:
        Marketing-angle, bridge-sentence, and call-to-action text.
    keywords:
        List of topic keywords.  ``None`` uses a built-in synthetic list.
    created_at:
        ISO-8601 creation timestamp.
    status:
        Project lifecycle status.
    include_angle, include_bridge, include_cta, include_keywords:
        Toggle inclusion of optional fields (used for minimal-record
        scenarios).

    Returns
    -------
    dict[str, Any]
        A single historical project record.
    """
    if keywords is None:
        keywords = [
            "AI 内容生产",
            "合成话题",
            "自动化",
            "效率提升",
            "壹目贯维",
        ]

    info: dict[str, Any] = {
        "project_id": project_id,
        "topic_id": topic_id,
        "source": source,
        "topic": topic,
        "topic_slug": topic_slug,
        "category": category,
        "created_at": created_at,
        "status": status,
        "videos": {},
        "articles": {},
        "publish": {},
    }

    if include_angle:
        info["angle"] = angle
    if include_bridge:
        info["bridge"] = bridge
    if include_cta:
        info["cta"] = cta
    if include_keywords:
        info["keywords"] = keywords

    return {
        "id": project_id,
        "info": info,
        "publish_log": {
            "status": "awaiting_publish",
            "updated_at": "2026-07-01T13:00:00",
            "platforms": {
                "wechat": {"status": "content_ready"},
                "zhihu": {"status": "content_ready"},
                "xiaohongshu": {"status": "content_ready"},
                "tiktok": {"status": "content_ready"},
                "bilibili": {"status": "content_ready"},
            },
            "videos": {
                "hyperframes_video": {
                    "path": _SYNTHETIC_VIDEO_PATH,
                    "duration": 60.0,
                    "file_size_mb": 2.5,
                    "status": "user_accepted",
                },
            },
        },
        "path": f"/tmp/hermes-projects/{project_id}",
    }


# ---------------------------------------------------------------------------
# Directory builders
# ---------------------------------------------------------------------------


def build_historical_project_dir(
    tmp_path: Path,
    form: str = "a",
    *,
    record: dict[str, Any] | None = None,
) -> Path:
    """Create a mock historical project directory under *tmp_path*.

    Two layout forms are supported:

    **Form A** (flat)::

        <project_dir>/
           00_project_info.json          # JSON dump of ``info``

    **Form B** (nested)::

        <project_dir>/
           00_project_info/
               project_info.json         # JSON dump of ``info``

    Parameters
    ----------
    tmp_path:
        Pytest ``tmp_path`` fixture (or any writable ``Path``).
    form:
        Layout variant — ``"a"`` (flat) or ``"b"`` (nested).
    record:
        Historical record dict; when ``None`` a default synthetic
        record is built via ``build_historical_record()``.

    Returns
    -------
    Path
        The created project directory path.

    Raises
    ------
    ValueError
        If *form* is not ``"a"`` or ``"b"``.
    """
    if form.lower() not in ("a", "b"):
        raise ValueError(f"form must be 'a' or 'b', got {form!r}")

    if record is None:
        record = build_historical_record()

    project_id = record["id"]
    project_dir = tmp_path / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    info = record["info"]

    if form.lower() == "a":
        # Flat: 00_project_info.json
        info_path = project_dir / "00_project_info.json"
        with open(info_path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=2)
    else:
        # Nested: 00_project_info/project_info.json
        info_dir = project_dir / "00_project_info"
        info_dir.mkdir(parents=True, exist_ok=True)
        info_path = info_dir / "project_info.json"
        with open(info_path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=2)

    return project_dir


def build_historical_project_dir_with_assets(
    tmp_path: Path,
    *,
    record: dict[str, Any] | None = None,
    form: str = "a",
) -> Path:
    """Create a mock historical project directory with media assets.

    In addition to the project-info file (see
    :func:`build_historical_project_dir`), this builder creates:

    * ``03_video/video_final.mp4``  (empty placeholder file)
    * ``05_publish/publish_log.json``  (publish-log data)

    Parameters
    ----------
    tmp_path:
        Pytest ``tmp_path`` fixture.
    record:
        Historical record dict; defaults to
        ``build_historical_record()``.
    form:
        Layout form — ``"a"`` (flat) or ``"b"`` (nested).

    Returns
    -------
    Path
        The created project directory path.
    """
    if record is None:
        record = build_historical_record()

    project_dir = build_historical_project_dir(tmp_path, form=form, record=record)

    # Create 03_video/video_final.mp4 (empty placeholder)
    video_dir = project_dir / "03_video"
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / "video_final.mp4"
    video_path.write_bytes(b"")

    # Create 05_publish/publish_log.json
    publish_dir = project_dir / "05_publish"
    publish_dir.mkdir(parents=True, exist_ok=True)
    publish_path = publish_dir / "publish_log.json"
    with open(publish_path, "w", encoding="utf-8") as fh:
        json.dump(record.get("publish_log", {}), fh, ensure_ascii=False, indent=2)

    return project_dir


# ---------------------------------------------------------------------------
# Edge-case builders
# ---------------------------------------------------------------------------


def build_malformed_project_dir(
    tmp_path: Path,
    *,
    form: str = "a",
) -> Path:
    """Create a project directory with malformed (invalid) JSON.

    The info file will contain raw text that is **not** valid JSON,
    allowing tests to verify that the compatibility scanner handles
    ``json.JSONDecodeError`` gracefully.

    Parameters
    ----------
    tmp_path:
        Pytest ``tmp_path`` fixture.
    form:
        Layout form — ``"a"`` (flat) or ``"b"`` (nested).

    Returns
    -------
    Path
        The created (malformed) project directory path.
    """
    project_id = "malformed-project-001"
    project_dir = tmp_path / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    malformed_content = (
        '{\n'
        '  "project_id": "malformed-project-001",\n'
        '  "topic": "This is not valid JSON...,\n'  # missing closing quote
        '  "created_at": "2026-07-01T12:00:00"\n'
        '}\n'
    )

    if form.lower() == "a":
        info_path = project_dir / "00_project_info.json"
    else:
        info_dir = project_dir / "00_project_info"
        info_dir.mkdir(parents=True, exist_ok=True)
        info_path = info_dir / "project_info.json"

    with open(info_path, "w", encoding="utf-8") as fh:
        fh.write(malformed_content)

    return project_dir


def build_minimal_project_dir(
    tmp_path: Path,
    *,
    form: str = "a",
) -> Path:
    """Create a project directory with only required info fields.

    Optional fields (``angle``, ``bridge``, ``cta``, ``keywords``) are
    omitted so tests can verify the scanner degrades gracefully when
    metadata is sparse.

    Parameters
    ----------
    tmp_path:
        Pytest ``tmp_path`` fixture.
    form:
        Layout form — ``"a"`` (flat) or ``"b"`` (nested).

    Returns
    -------
    Path
        The created minimal project directory path.
    """
    record = build_historical_record(
        include_angle=False,
        include_bridge=False,
        include_cta=False,
        include_keywords=False,
    )
    return build_historical_project_dir(tmp_path, form=form, record=record)
