"""MCP tool for content analytics.

Provides ``analyze_content`` for use as an MCP tool registered in
the AutoMedia MCP server.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def analyze_content(
    project_id: str,
    base_dir: str = "",
) -> dict[str, Any]:
    """Compute content analytics for a project.

    Scans the project's ``01_content/drafts/`` for markdown files and
    computes word count, sentiment, readability, and brand mentions.

    Parameters
    ----------
    project_id:
        The project ID to analyse.
    base_dir:
        Base directory to scan for projects.  Defaults to the current
        working directory when empty.

    Returns
    -------
    dict
        ``{"status": "ok", "project_id": ..., "stats": {...}}``
        or ``{"status": "error", "error": ...}`` on failure.
    """
    try:
        if not project_id:
            return {"status": "error", "error": "project_id is required"}

        base = Path(base_dir) if base_dir else Path.cwd()

        # Find project by ID
        project_info: dict[str, Any] | None = None
        for info_file in sorted(base.glob("*/00_project_info.json")):
            try:
                data = json.loads(info_file.read_text(encoding="utf-8"))
                if data.get("project_id") == project_id:
                    data["_dir"] = str(info_file.parent)
                    project_info = data
                    break
            except (json.JSONDecodeError, OSError):
                continue

        if project_info is None:
            return {"status": "error", "error": f"Project not found: {project_id}"}

        # Read content from drafts
        project_dir = Path(project_info["_dir"])
        drafts_dir = project_dir / "01_content" / "drafts"
        content = ""
        if drafts_dir.is_dir():
            parts: list[str] = []
            for md_file in sorted(drafts_dir.glob("*.md")):
                try:
                    parts.append(md_file.read_text(encoding="utf-8"))
                except OSError:
                    continue
            content = "\n\n".join(parts)

        # Compute stats
        from automedia.effects.stats import (
            brand_mention_frequency,
            readability_index,
            sentiment_score,
            word_count,
        )

        brand_name = project_info.get("brand", "")
        wc = word_count(content)
        ss = sentiment_score(content)
        ri = readability_index(content)
        bmf = (
            brand_mention_frequency(content, [brand_name])
            if brand_name
            else {"mentions": {}, "total_mentions": 0}
        )

        return {
            "status": "ok",
            "project_id": project_id,
            "topic": project_info.get("topic", ""),
            "brand": brand_name,
            "stats": {
                "word_count": wc,
                "sentiment": ss,
                "readability": ri,
                "brand_mentions": bmf,
            },
        }

    except Exception as exc:
        return {"status": "error", "error": str(exc)}
