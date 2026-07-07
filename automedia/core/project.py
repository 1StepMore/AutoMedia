"""Project initialization — directory structure, slug sanitization, path safety."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Slug / path utilities
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert *text* into a safe URL-friendly slug.

    * Lowercases the string.
    * Replaces whitespace and underscores with hyphens.
    * Removes all characters except ``[a-z0-9-]`` (CJK and other non-ASCII
      characters are stripped).
    * Collapses consecutive hyphens.
    * Strips leading/trailing hyphens.

    Examples
    --------
    >>> _slugify("Hello World")
    'hello-world'
    >>> _slugify("AutoMedia 2024 项目启动")
    'automedia-2024'
    >>> _slugify("  __foo__bar__  ")
    'foo-bar'
    """
    text = text.lower()
    # Replace whitespace / underscores with a hyphen
    text = re.sub(r"[\s_]+", "-", text)
    # Strip everything except a-z, 0-9, hyphens (removes CJK etc.)
    text = re.sub(r"[^a-z0-9-]", "", text)
    # Collapse multiple hyphens
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def sanitize_path(path: str) -> str:
    """Validate and normalise a filesystem path component.

    Raises ``ValueError`` if *path* contains path-traversal patterns
    (``..``), home-directory shortcuts (``~``), or redundant slashes
    (``//``).

    Returns the normalised absolute path via ``os.path.realpath``.

    Examples
    --------
    >>> sanitize_path("/valid/path")
    '/valid/path'
    >>> sanitize_path("../etc")
    ValueError: ...
    """
    if not path:
        raise ValueError("Path must not be empty")
    if ".." in path:
        raise ValueError(f"Path must not contain '..': {path!r}")
    if "~" in path:
        raise ValueError(f"Path must not contain '~': {path!r}")
    if "//" in path:
        raise ValueError(f"Path must not contain '//': {path!r}")
    return os.path.realpath(path)


# ---------------------------------------------------------------------------
# Project dataclass
# ---------------------------------------------------------------------------

@dataclass
class Project:
    """A media project with a standardised directory layout.

    Attributes
    ----------
    project_id:
        Short unique identifier (``uuid4().hex[:12]``).
    project_dir:
        Absolute path to the project root directory.
    topic:
        Original topic string (as passed to ``init()``).
    brand:
        Brand identifier (validated for path safety).
    tenant_id:
        Tenant / namespace identifier.
    created_at:
        ISO-8601 timestamp of creation.
    """

    project_id: str
    project_dir: str
    topic: str
    brand: str
    tenant_id: str
    created_at: str

    @classmethod
    def init(
        cls,
        topic_slug: str,
        brand: str,
        *,
        tenant_id: str = "default",
        base_dir: str | None = None,
    ) -> Project:
        """Create a new project with a standard directory structure.

        Parameters
        ----------
        topic_slug:
            Raw topic string; will be slugified for the directory name.
        brand:
            Brand identifier (validated for path safety).
        tenant_id:
            Tenant / namespace identifier.  Defaults to ``"default"``.
        base_dir:
            Parent directory for the project.  When ``None`` the current
            working directory is used.

        Returns
        -------
        Project
            A new ``Project`` instance.

        Raises
        ------
        ValueError
            If *brand* or *base_dir* contain path-traversal patterns, or
            if the slugified *topic_slug* is empty.
        """
        slug = _slugify(topic_slug)
        if not slug:
            raise ValueError(
                f"topic_slug {topic_slug!r} produces empty slug after sanitisation"
            )

        brand_clean = sanitize_path(brand) if brand != "" else brand

        if base_dir is None:
            base_dir = os.getcwd()
        base_dir = sanitize_path(base_dir)

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        dirname = f"{today}_{slug}"
        project_dir = os.path.join(base_dir, dirname)

        # Create standard directory structure
        root = Path(project_dir)
        subdirs = [
            "01_content/drafts",
            "02_images/cover",
            "03_video",
            "04_subtitle",
            "05_review",
            "06_publish",
        ]
        for sub in subdirs:
            (root / sub).mkdir(parents=True, exist_ok=True)

        # Metadata
        project_id = uuid.uuid4().hex[:12]
        created_at = datetime.now(timezone.utc).isoformat()

        info = {
            "project_id": project_id,
            "topic": topic_slug,
            "brand": brand,
            "tenant_id": tenant_id,
            "created_at": created_at,
        }

        info_path = root / "00_project_info.json"
        with open(info_path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=2)

        return cls(
            project_id=project_id,
            project_dir=str(root.resolve()),
            topic=topic_slug,
            brand=brand,
            tenant_id=tenant_id,
            created_at=created_at,
        )
