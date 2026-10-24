"""Project initialization — directory structure, slug sanitization, path safety."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from automedia.core.asset_pack import pull_video_assets
from automedia.core.env_overlay import env_lookup
from automedia.core.layout import PROJECT_SUBDIRS

_log = logging.getLogger(__name__)

# Project identity file — one JSON blob per project directory.  ``_discover``
# globs one level deep (project dirs are direct children of the base dir).
_INFO_FILENAME = "00_project_info.json"
_PROJECT_INFO_GLOB = f"*/{_INFO_FILENAME}"

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


# Readable alphabet: CJK (Han, Hiragana, Katakana, Hangul).  ``sanitize_path``
# accepts Unicode path components, so a CJK topic can keep its own characters
# instead of vanishing.  One source of truth for both slug helpers below.
_CJK_RANGES = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7a3"

# Readable fallback alphabet: ASCII alphanumerics plus CJK.
_CJK_SLUG_RE = re.compile(rf"[^a-z0-9{_CJK_RANGES}-]")

# Same alphabet without ASCII, used to isolate the CJK segment of a mixed
# topic (see :func:`_cjk_part`).
_CJK_ONLY_RE = re.compile(rf"[^{_CJK_RANGES}-]")

# Cap the readable fallback so a very long CJK topic cannot exceed the
# filesystem's 255-byte component limit (UTF-8 CJK is 3 bytes/char).
_SLUG_MAX_LEN = 60

# Code points reserved for the CJK segment of a mixed Latin/CJK slug.  Without
# a reserve a long Latin prefix spends the entire budget and truncates the CJK
# segment away, which brings back the very collisions issue #256 is about.
_SLUG_CJK_RESERVE = 20

# Hard ceiling in UTF-8 bytes: filesystem components allow 255 and
# ``Project.init`` prefixes ``YYYYMMDD_`` (9 bytes).  The code-point caps above
# keep CJK slugs at <= 180 bytes, so this guard only bites long Latin topics.
_SLUG_MAX_BYTES = 200


def _readable(text: str, alphabet: re.Pattern[str]) -> str:
    cleaned = re.sub(r"[\s_]+", "-", text.lower())
    cleaned = alphabet.sub("", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned[:_SLUG_MAX_LEN].strip("-")


def _clip_bytes(slug: str, limit: int = _SLUG_MAX_BYTES) -> str:
    if len(slug.encode("utf-8")) <= limit:
        return slug
    kept: list[str] = []
    used = 0
    for char in slug:
        size = len(char.encode("utf-8"))
        if used + size > limit:
            break
        kept.append(char)
        used += size
    return "".join(kept).strip("-")


def _fallback_slug(text: str) -> str:
    """Deterministic, always-non-empty slug for topics :func:`_slugify` drops.

    Two-tier strategy:

    1. **Readable** — keep CJK characters (see ``_CJK_SLUG_RE``) so a
       Chinese/Japanese/Korean topic still yields an identifiable directory.
    2. **Hash** — when nothing readable survives (pure symbols, emoji, empty
       string), fall back to ``topic-<sha1(original)[:8]>``.  The digest is
       computed over the *original* text, so the same input always yields the
       same slug and renders are reproducible.
    """
    readable = _readable(text, _CJK_SLUG_RE)
    if readable:
        return readable

    digest = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[
        :8
    ]  # non-crypto slug digest
    return f"topic-{digest}"


def _cjk_part(text: str) -> str:
    """Return the sanitised CJK-only segment of *text*.

    Mirrors :func:`_fallback_slug`'s readable branch but keeps only CJK
    characters (ASCII letters/digits are dropped), so callers can combine the
    Latin and CJK portions of a mixed topic without losing either one.
    """
    return _readable(text, _CJK_ONLY_RE)


def slugify_topic(text: str) -> str:
    """Return a non-empty, deterministic slug for *text*.

    Latin-only topics keep the historical :func:`_slugify` result, clipped to
    ``_SLUG_MAX_BYTES`` so the directory name stays inside the filesystem's
    255-byte component limit.  Mixed Latin/CJK topics keep both parts, Latin
    first and CJK second, joined by a hyphen (e.g. ``automedia-2024-项目启动``).
    The Latin prefix is clipped to leave ``_SLUG_CJK_RESERVE`` code points for
    the CJK segment, so distinct Chinese topics sharing an English suffix do
    not collapse onto the same directory.  Pure-CJK topics keep their
    characters, and topics that sanitise to nothing (pure punctuation, empty
    string) fall through to :func:`_fallback_slug`, which emits a reproducible
    hash.
    """
    ascii_part = _slugify(text)
    cjk_part = _cjk_part(text)

    if ascii_part and cjk_part:
        ascii_budget = _SLUG_MAX_LEN - _SLUG_CJK_RESERVE - 1
        ascii_part = ascii_part[:ascii_budget].strip("-")
        cjk_budget = _SLUG_MAX_LEN - len(ascii_part) - 1
        cjk_part = cjk_part[:cjk_budget].strip("-")
        slug = f"{ascii_part}-{cjk_part}" if cjk_part else ascii_part
    elif ascii_part:
        slug = ascii_part
    elif cjk_part:
        slug = cjk_part
    else:
        slug = _fallback_slug(text)
    return _clip_bytes(slug)


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
            Parent directory for the project.  When ``None`` the
            ``AUTOMEDIA_PROJECTS_DIR`` environment variable is checked
            first; if that is also unset the current working directory
            is used.

        Returns
        -------
        Project
            A new ``Project`` instance.

        Raises
        ------
        ValueError
            If *brand* or *base_dir* contain path-traversal patterns.
        """
        slug = slugify_topic(topic_slug)

        # Validate brand for path safety (call has side effect — raises ValueError)
        if not brand:
            raise ValueError(f"brand must not be empty, got {brand!r}")
        sanitize_path(brand)

        if base_dir is None:
            env_dir = env_lookup("AUTOMEDIA_PROJECTS_DIR", "")
            base_dir = str(Path(env_dir).resolve()) if env_dir else os.getcwd()
        base_dir = sanitize_path(base_dir)

        today = datetime.now(UTC).strftime("%Y%m%d")
        dirname = f"{today}_{slug}"
        project_dir = os.path.join(base_dir, dirname)

        # Create standard directory structure.  The list lives in
        # ``core.layout`` — one source of truth shared with every writer, so a
        # path cannot be written to without also being created (issue #284).
        root = Path(project_dir)
        for sub in PROJECT_SUBDIRS:
            (root / sub).mkdir(parents=True, exist_ok=True)

        try:
            pull_video_assets(project_dir)
        except Exception as exc:
            _log.warning("Could not pull video asset pack for %s: %s", project_dir, exc)

        # Metadata
        project_id = uuid.uuid4().hex[:12]
        created_at = datetime.now(UTC).isoformat()

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

    @classmethod
    def load(cls, project_dir: str) -> Project:
        """Load an existing project from *project_dir*'s info file.

        Unlike :meth:`init` this never mints a new ``project_id``; it restores
        the persisted identity so a parked project can be resumed.

        Raises
        ------
        FileNotFoundError
            If ``00_project_info.json`` is absent.
        ValueError
            If the info file is unreadable/corrupt or lacks ``project_id``.
        """
        info_path = Path(project_dir) / _INFO_FILENAME
        if not info_path.is_file():
            raise FileNotFoundError(f"No project info file: {info_path}")
        try:
            with open(info_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except OSError as exc:
            raise ValueError(f"Unreadable project info: {info_path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt project info: {info_path}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Project info is not an object: {info_path}")
        project_id = data.get("project_id")
        if not project_id:
            raise ValueError(f"Project info is missing 'project_id': {info_path}")

        return cls(
            project_id=str(project_id),
            project_dir=str(Path(project_dir).resolve()),
            topic=str(data.get("topic", "")),
            brand=str(data.get("brand", "")),
            tenant_id=str(data.get("tenant_id", "default")),
            created_at=str(data.get("created_at", "")),
        )


def find_project_dir(project_id: str, base_dir: str | None = None) -> str | None:
    """Return the directory of the project whose id is *project_id*, or ``None``.

    Scans the base directory (`base_dir`, else ``AUTOMEDIA_PROJECTS_DIR`` from
    env or the ``.env`` overlay, else the cwd) one level deep for a matching
    ``00_project_info.json``.
    """
    root = base_dir or env_lookup("AUTOMEDIA_PROJECTS_DIR", "") or os.getcwd()
    base = Path(sanitize_path(root))
    for info_file in sorted(base.glob(_PROJECT_INFO_GLOB)):
        try:
            with open(info_file, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            # A corrupt/removed candidate must not abort the search; it simply
            # is not the target. Narrowed to parse/IO so real bugs still surface.
            _log.debug("Skipping unreadable project info %s: %s", info_file, exc)
            continue
        if isinstance(data, dict) and data.get("project_id") == project_id:
            return str(info_file.parent)
    return None
